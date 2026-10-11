import com.cburch.logisim.file.*;
import com.cburch.logisim.proj.*;
import com.cburch.logisim.circuit.*;
import com.cburch.logisim.comp.*;
import com.cburch.logisim.data.*;
import com.cburch.logisim.instance.*;
import com.cburch.logisim.std.wiring.Pin;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.*;
import java.util.*;
import javax.swing.JPanel;
import javax.imageio.ImageIO;
import javax.xml.parsers.*;
import org.w3c.dom.*;

/** Deterministic PNG export of an isolated, real Logisim simulation state. */
public class CircuitImage {
 static Circuit circuit; static CircuitState state;
 static Map<String,com.cburch.logisim.comp.Component> pins=new LinkedHashMap<>();
 static void inputs(Element step) {
  NodeList values=step.getElementsByTagName("pin");
  for(int i=0;i<values.getLength();i++){
   Element value=(Element)values.item(i);String label=value.getAttribute("label");
   com.cburch.logisim.comp.Component c=pins.get(label);
   if(c==null)throw new IllegalArgumentException("Unknown input pin: "+label);
   Instance inst=Instance.getInstanceFor(c);
   if(!Pin.FACTORY.isInputPin(inst))throw new IllegalArgumentException("Cannot drive output pin: "+label);
   long v=Long.parseLong(value.getAttribute("value"));int width=Pin.FACTORY.getWidth(inst).getWidth();
   if(v<0 || v>=(1L<<width))throw new IllegalArgumentException("Input value out of range: "+label+" width="+width);
   Pin.FACTORY.setValue(state.getInstanceState(c),Value.createKnown(BitWidth.create(width),(int)v));state.markComponentAsDirty(c);
  }
  settle();
 }
 static void settle(){state.getPropagator().propagate();if(state.getPropagator().isOscillating())throw new IllegalStateException("Simulation oscillates");}
 public static void main(String[] args) {
  try{
   DocumentBuilderFactory df=DocumentBuilderFactory.newInstance();df.setFeature("http://apache.org/xml/features/disallow-doctype-decl",true);
   Element request=df.newDocumentBuilder().parse(new File(args[1])).getDocumentElement();
   LogisimFile f=new PortProbe.StrictLoader().openLogisimFile(new File(args[0]));
   circuit=f.getCircuit(request.getAttribute("circuit"));if(circuit==null)throw new IllegalArgumentException("Unknown circuit");
   Project project=new Project(f);state=project.getCircuitState(circuit);
   for(com.cburch.logisim.comp.Component c:circuit.getNonWires())if(c.getFactory()==Pin.FACTORY){
    String label=c.getAttributeSet().getValue(StdAttr.LABEL);
    if(!label.isEmpty() && pins.put(label,c)!=null)throw new IllegalArgumentException("Ambiguous pin label: "+label);
   }
   settle();NodeList steps=request.getElementsByTagName("step");
   for(int i=0;i<steps.getLength();i++)inputs((Element)steps.item(i));
   int ticks=Integer.parseInt(request.getAttribute("ticks"));
   for(int i=0;i<ticks;i++){state.getPropagator().tick();settle();}
   int scale=Integer.parseInt(request.getAttribute("scale")),pad=Integer.parseInt(request.getAttribute("padding"));
   BufferedImage scratch=new BufferedImage(1,1,BufferedImage.TYPE_INT_RGB);Graphics2D sg=scratch.createGraphics();Bounds b=circuit.getBounds(sg);sg.dispose();
   long width=(b.getWidth()+2L*pad)*scale,height=(b.getHeight()+2L*pad)*scale;
   if(width<1 || height<1 || width*height>24000000L)throw new IllegalArgumentException("Image exceeds 24 million pixels; reduce scale or circuit extent");
   BufferedImage img=new BufferedImage((int)width,(int)height,BufferedImage.TYPE_INT_RGB);Graphics2D g=img.createGraphics();
   g.setColor(Color.WHITE);g.fillRect(0,0,(int)width,(int)height);g.scale(scale,scale);g.translate(pad-b.getX(),pad-b.getY());g.setColor(Color.BLACK);
   g.setRenderingHint(RenderingHints.KEY_ANTIALIASING,RenderingHints.VALUE_ANTIALIAS_ON);
   ComponentDrawContext ctx=new ComponentDrawContext(new JPanel(),circuit,state,g,g){public Object getGateShape(){return "shaped";}};
   ctx.setShowState(Boolean.parseBoolean(request.getAttribute("show_state")));ctx.setShowColor(true);circuit.draw(ctx,Collections.emptySet());g.dispose();
   if(!ImageIO.write(img,"png",new File(args[2])))throw new IOException("PNG encoder unavailable");
   Map<String,Object> pinValues=new LinkedHashMap<>();
   for(Map.Entry<String,com.cburch.logisim.comp.Component> p:pins.entrySet()){
    Value v=Pin.FACTORY.getValue(state.getInstanceState(p.getValue()));
    pinValues.put(p.getKey(),v.toHexString());
   }
   java.util.List<Object> layoutComponents=new ArrayList<>();
   for(com.cburch.logisim.comp.Component c:circuit.getNonWires()){
    Bounds cb=c.getBounds();AttributeSet ca=c.getAttributeSet();Map<String,Object> attributes=new LinkedHashMap<>();
    for(Attribute<?> attribute:ca.getAttributes())if(attribute.getName().equals("label"))attributes.put("label",ca.getValue(attribute));
    layoutComponents.add(PortProbe.obj("name",c.getFactory().getName(),"loc",c.getLocation().toString(),"attributes",attributes,
     "bounds",PortProbe.obj("x",cb.getX(),"y",cb.getY(),"width",cb.getWidth(),"height",cb.getHeight())));
   }
   System.out.println(PortProbe.json(PortProbe.obj("width",width,"height",height,"pin_values",pinValues,"ticks",ticks,"steps",steps.getLength(),"layout_components",layoutComponents)));
  }catch(Throwable t){t.printStackTrace(System.err);System.exit(2);}
  System.exit(0);
 }
}
