import com.cburch.logisim.circuit.Propagator;
import com.cburch.logisim.data.Value;
import java.io.*;
import java.lang.reflect.*;
import java.util.*;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.*;

/** Records the installed engine's propagation events, never a replacement simulator. */
public class PropagationTrace extends CircuitImage {
 static String csv(String s){return "\""+s.replace("\"","\"\"")+"\"";}
 static Element child(Element root,String tag){return (Element)root.getElementsByTagName(tag).item(0);}
 static String[] sample(java.util.List<String> names){
  String[] values=new String[names.size()];
  for(int i=0;i<names.size();i++)values[i]=state.getValue(pins.get(names.get(i)).getLocation()).toHexString();
  return values;
 }
 static void row(PrintWriter csv,int n,long time,String[] values){
  csv.print(n+","+time);for(String v:values)csv.print(","+v);csv.println();
 }
 public static void main(String[] args){
  try {
   DocumentBuilderFactory df=DocumentBuilderFactory.newInstance();df.setFeature("http://apache.org/xml/features/disallow-doctype-decl",true);
   Element req=df.newDocumentBuilder().parse(new File(args[1])).getDocumentElement();
   load(new File(args[0]),req.getAttribute("circuit"));
   inputs(child(req,"initial"));
   java.util.List<String> names=new ArrayList<>();NodeList signals=req.getElementsByTagName("signal");
   Map<String,Object> widths=new LinkedHashMap<>();
   for(int i=0;i<signals.getLength();i++){
    String label=((Element)signals.item(i)).getAttribute("label");
    if(!pins.containsKey(label)||names.contains(label))throw new IllegalArgumentException("Missing or duplicate signal: "+label);
    names.add(label);widths.put(label,com.cburch.logisim.std.wiring.Pin.FACTORY.getWidth(com.cburch.logisim.instance.Instance.getInstanceFor(pins.get(label))).getWidth());
   }
   Field clock,queue;Method step;
   try {
    clock=Propagator.class.getDeclaredField("clock");queue=Propagator.class.getDeclaredField("toProcess");
    step=Propagator.class.getDeclaredMethod("step",Class.forName("com.cburch.logisim.circuit.PropagationPoints"));
    clock.setAccessible(true);queue.setAccessible(true);step.setAccessible(true);
   }catch(ReflectiveOperationException e){throw new IllegalStateException("This runtime does not expose the verified propagation bridge API",e);}
   Propagator prop=state.getPropagator();int base=clock.getInt(prop);
   java.util.List<Long> times=new ArrayList<>();java.util.List<String[]> samples=new ArrayList<>();
   Set<Long> wanted=new LinkedHashSet<>();NodeList captures=req.getElementsByTagName("capture");
   for(int i=0;i<captures.getLength();i++)wanted.add(Long.parseLong(((Element)captures.item(i)).getAttribute("time")));
   Map<Long,String> captured=new LinkedHashMap<>();File output=new File(args[2]);
   long time=0;int count=0,max=Integer.parseInt(req.getAttribute("max_events"));long maxTime=Long.parseLong(req.getAttribute("max_time"));
   String verdict="event_limit";
   try(PrintWriter w=new PrintWriter(new File(output,"trace.csv"),"UTF-8")){
    w.print("event_index,engine_time_from_request");for(String n:names)w.print(","+csv(n));w.println();
    String[] values=sample(names);samples.add(values);times.add(0L);row(w,0,0,values);
    if(wanted.contains(0L)){String name="capture-0.png";render(req,new File(output,name));captured.put(0L,name);}
    drive(child(req,"change"));
    while(count<max){
     // Dirty input components enter the event queue during the first step.
     // An empty queue immediately after drive() does not mean no work exists.
     if(count>0&&((Queue<?>)queue.get(prop)).isEmpty()){verdict="settled";break;}
     step.invoke(prop,new Object[]{null});count++;time=(long)clock.getInt(prop)-base;
     values=sample(names);samples.add(values);times.add(time);row(w,count,time,values);
     if(time>maxTime){verdict="time_limit";break;}
     if(wanted.contains(time)){String name="capture-"+time+".png";render(req,new File(output,name));captured.put(time,name);}
    }
    if(((Queue<?>)queue.get(prop)).isEmpty()&&time<=maxTime)verdict="settled";
    if(w.checkError())throw new IOException("Failed to write propagation CSV");
   }
   boolean complete=verdict.equals("settled");String anchor=req.getAttribute("anchor_signal");Long anchorTime=null;
   if(!anchor.isEmpty()){
    int ix=names.indexOf(anchor);if(ix<0)throw new IllegalArgumentException("Anchor signal must be selected");
    for(int i=1;i<samples.size();i++)if(!samples.get(i)[ix].equals(samples.get(0)[ix])){anchorTime=times.get(i);break;}
   }
   Map<String,Object> summaries=new LinkedHashMap<>();
   for(int col=0;col<names.size();col++){
    String initial=samples.get(0)[col],last=samples.get(samples.size()-1)[col];Long firstChange=null,lastChange=null;int lastBad=-1;
    for(int i=0;i<samples.size();i++){
     if(!samples.get(i)[col].equals(last))lastBad=i;
     if(i>0&&!samples.get(i)[col].equals(samples.get(i-1)[col])){if(firstChange==null)firstChange=times.get(i);lastChange=times.get(i);}
    }
    Long stable=complete?times.get(lastBad+1):null;
    Value value=state.getValue(pins.get(names.get(col)).getLocation());
    summaries.put(names.get(col),PortProbe.obj("width",widths.get(names.get(col)),"initial",initial,"final",last,"fully_defined",value.isFullyDefined(),"changed",firstChange!=null,
      "first_change_time",firstChange,"last_change_time",lastChange,"final_stable_time",stable,
      "first_change_delay_from_anchor",anchorTime==null||firstChange==null?null:firstChange-anchorTime,
      "final_stable_delay_from_anchor",anchorTime==null||stable==null?null:stable-anchorTime));
   }
   java.util.List<Object> images=new ArrayList<>();for(Map.Entry<Long,String> item:captured.entrySet())images.add(PortProbe.obj("engine_time_from_request",item.getKey(),"file",item.getValue()));
   java.util.List<Object> missed=new ArrayList<>();for(Long t:wanted)if(!captured.containsKey(t))missed.add(t);
   Map<String,Object> metadata=PortProbe.obj("complete",complete,"verdict",verdict,"event_count",count,"sample_count",samples.size(),"last_engine_time",time,"queue_empty_time",complete?time:null,
    "time_origin","input request; no conversion to physical time","anchor_signal",anchor.isEmpty()?null:anchor,"anchor_first_change_time",anchorTime,"signals",summaries,"captures",images,"capture_times_not_observed",missed,
    "pending_events",((Queue<?>)queue.get(prop)).size());
   System.out.println(PortProbe.json(metadata));
  }catch(Throwable t){t.printStackTrace(System.err);System.exit(2);}
  System.exit(0);
 }
}
