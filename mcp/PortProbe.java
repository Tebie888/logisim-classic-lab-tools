import com.cburch.logisim.file.*;
import com.cburch.logisim.tools.*;
import com.cburch.logisim.comp.*;
import com.cburch.logisim.circuit.*;
import com.cburch.logisim.data.*;
import com.cburch.logisim.instance.*;
import java.io.*;
import java.util.*;
import javax.xml.parsers.*;
import org.w3c.dom.*;

/** Runtime metadata bridge, compiled for Java 8. stdout is one JSON value. */
public class PortProbe {
  static class StrictLoader extends Loader {
    StrictLoader() { super(null); }
    @Override public void showError(String message) { throw new IllegalArgumentException(message); }
  }
  static String json(Object o) {
    if(o == null) return "null";
    if(o instanceof Number || o instanceof Boolean) return o.toString();
    if(o instanceof Map) {
      List<String> parts = new ArrayList<>();
      for(Object k : ((Map<?,?>)o).keySet()) parts.add(json(k)+":"+json(((Map<?,?>)o).get(k)));
      return "{"+String.join(",", parts)+"}";
    }
    if(o instanceof Iterable) {
      List<String> parts = new ArrayList<>();
      for(Object v : (Iterable<?>)o) parts.add(json(v));
      return "["+String.join(",", parts)+"]";
    }
    StringBuilder b=new StringBuilder("\"");
    for(char ch : o.toString().toCharArray()) {
      if(ch=='"' || ch=='\\') b.append('\\').append(ch);
      else if(ch<32) b.append(String.format("\\u%04x", (int)ch));
      else b.append(ch);
    }
    return b.append('"').toString();
  }
  static Map<String,Object> obj(Object... kv) {
    Map<String,Object> m=new LinkedHashMap<>();
    for(int i=0;i<kv.length;i+=2) m.put((String)kv[i],kv[i+1]);
    return m;
  }
  @SuppressWarnings({"rawtypes","unchecked"})
  static String standard(Attribute a,Object v) { return v==null ? null : a.toStandardString(v); }
  static Map<String,Object> attrs(AttributeSet s) {
    Map<String,Object> m=new LinkedHashMap<>();
    for(Attribute<?> a : s.getAttributes()) {
      if(s.isToSave(a)) m.put(a.getName(),standard(a,s.getValue(a)));
    }
    return m;
  }
  static List<Object> ports(Component c) {
    List<Object> out=new ArrayList<>(); int i=0;
    Instance inst=Instance.getInstanceFor(c);
    for(EndData e : c.getEnds()) {
      String hint=inst!=null && i<inst.getPorts().size() ? inst.getPorts().get(i).getToolTip() : null;
      out.add(obj("index",i++,"loc",e.getLocation().toString(), "tooltip",hint,
        "width",e.getWidth().getWidth(),"input",e.isInput(),"output",e.isOutput()));
    }
    return out;
  }
  static Object catalog(Loader l) {
    List<Object> out=new ArrayList<>();
    for(Library lib : l.getBuiltin().getLibraries()) for(Tool t : lib.getTools()) {
      if(t instanceof AddTool) {
        ComponentFactory f=((AddTool)t).getFactory();
        out.add(obj("library","#"+lib.getName(),"name",t.getName(),"factory_name",f.getName(),"defaults",attrs(f.createAttributeSet())));
      }
    }
    String version=com.cburch.logisim.Main.VERSION.toString();
    return obj("components",out,"runtime_version",version,"source",version.replaceFirst("\\.exe$",""));
  }
  @SuppressWarnings({"rawtypes","unchecked"})
  static Object inspect(Loader l,String file) throws Exception {
    // Headless loading fails on unresolved libraries/components rather than showing dialogs.
    LogisimFile f=l.openLogisimFile(new File(file));
    DocumentBuilderFactory df=DocumentBuilderFactory.newInstance();
    df.setFeature("http://apache.org/xml/features/disallow-doctype-decl",true);
    Document d=df.newDocumentBuilder().parse(new File(file));
    Map<String,Library> libraries=new HashMap<>();
    NodeList libnodes=d.getDocumentElement().getElementsByTagName("lib");
    for(int i=0;i<libnodes.getLength();i++) {
      Element lib=(Element)libnodes.item(i);
      libraries.put(lib.getAttribute("name"),l.loadLibrary(lib.getAttribute("desc")));
    }
    List<Object> result=new ArrayList<>();
    NodeList circuits=d.getDocumentElement().getElementsByTagName("circuit");
    for(int ci=0;ci<circuits.getLength();ci++) {
      Element xml=(Element)circuits.item(ci);
      Circuit c=f.getCircuit(xml.getAttribute("name"));
      if(c==null) throw new Exception("Circuit missing: "+xml.getAttribute("name"));
      List<Object> comps=new ArrayList<>();
      NodeList nodes=xml.getElementsByTagName("comp");
      if(c.getNonWires().size()!=nodes.getLength()) throw new Exception("Runtime component count differs in "+c.getName());
      for(int n=0;n<nodes.getLength();n++) {
        Element x=(Element)nodes.item(n); Component found=null;
        ComponentFactory expectedFactory=null;
        Library library=libraries.get(x.getAttribute("lib"));
        if(library!=null) {
          Tool tool=library.getTool(x.getAttribute("name"));
          if(tool instanceof AddTool) expectedFactory=((AddTool)tool).getFactory();
        } else if(f.getCircuit(x.getAttribute("name"))!=null) expectedFactory=f.getCircuit(x.getAttribute("name")).getSubcircuitFactory();
        for(Component candidate : c.getNonWires()) if(candidate.getFactory()==expectedFactory
          && candidate.getLocation().equals(Location.parse(x.getAttribute("loc")))) {
          if(found!=null) throw new Exception("Ambiguous component location/name");
          found=candidate;
        }
        if(found==null) throw new Exception("Component missing: "+x.getAttribute("name"));
        AttributeSet s=found.getAttributeSet();
        NodeList aa=x.getElementsByTagName("a");
        for(int ai=0;ai<aa.getLength();ai++) {
          Element ax=(Element)aa.item(ai); Attribute a=s.getAttribute(ax.getAttribute("name"));
          if(a==null) throw new Exception("Unknown attribute "+x.getAttribute("name")+"."+ax.getAttribute("name"));
          String value=ax.hasAttribute("val") ? ax.getAttribute("val") : ax.getTextContent();
          Object parsed=a.parse(value);
          if(parsed instanceof BitWidth && (((BitWidth)parsed).getWidth()<1 || ((BitWidth)parsed).getWidth()>32))
            throw new Exception("Bit width must be 1..32: "+a.getName());
          if(parsed==null || !Objects.equals(standard(a,parsed),standard(a,s.getValue(a))))
            throw new Exception("Invalid or ignored attribute "+x.getAttribute("name")+"."+a.getName()+"="+value);
          Object current=s.getValue(a);
          if(current instanceof Boolean && !value.equals("true") && !value.equals("false"))
            throw new Exception("Invalid boolean "+a.getName());
        }
        Bounds b=found.getBounds();
        comps.add(obj("name",x.getAttribute("name"),"factory_name",found.getFactory().getName(),"loc",found.getLocation().toString(),
          "ports",ports(found),"attributes",attrs(s),"bounds",obj("x",b.getX(),"y",b.getY(),"width",b.getWidth(),"height",b.getHeight())));
      }
      c.getWidth(Location.create(0,0)); // Initialize the wire map before querying conflicts.
      Set<WidthIncompatibilityData> conflicts=c.getWidthIncompatibilityData();
      List<Object> conflictPoints=new ArrayList<>();
      if(conflicts!=null) for(WidthIncompatibilityData conflict:conflicts) {
        List<Object> points=new ArrayList<>();
        for(int i=0;i<conflict.size();i++)points.add(obj("loc",conflict.getPoint(i).toString(),"width",conflict.getBitWidth(i).getWidth()));
        conflictPoints.add(points);
      }
      List<Object> columns=new ArrayList<>();
      for(Map.Entry<Instance,String> pin : Analyze.getPinLabels(c).entrySet()) {
        Instance inst=pin.getKey(); String label=pin.getValue();
        if(!com.cburch.logisim.std.wiring.Pin.FACTORY.isInputPin(inst) && !label.equals("halt") && !label.equals("_passed")) {
          int width=com.cburch.logisim.std.wiring.Pin.FACTORY.getWidth(inst).getWidth();
          int field=(width+3)/4+5;
          StringBuilder padded=new StringBuilder(label.length()>field ? label.substring(0,field) : label);
          while(padded.length()<field) padded.append(' ');
          columns.add(obj("label",label,"loc",inst.getLocation().toString(),"width",width,"field_width",field,"header_field",padded.toString()));
        }
      }
      result.add(obj("name",c.getName(),"components",comps,"width_conflicts",conflicts==null ? 0 : conflicts.size(),"width_conflict_points",conflictPoints,"tty_columns",columns));
    }
    return obj("circuits",result);
  }
  public static void main(String[] args) {
    try {
      Loader l=new StrictLoader();
      System.out.println(json(args[0].equals("catalog") ? catalog(l) : inspect(l,args[1])));
    } catch(Throwable e) { e.printStackTrace(System.err); System.exit(2); }
    System.exit(0); // Stop Logisim's background threads.
  }
}
