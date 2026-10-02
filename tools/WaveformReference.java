/* Offline test harness only. Does not instantiate a device or controller Main.
 * Every attempted hardware operation on the FPGA proxy throws immediately.
 */
import java.nio.file.*;
import java.lang.reflect.*;
import java.util.*;
import com.google.gson.*;
import sun.misc.Unsafe;
import chrisblaster.ChrisBlasterProtocol;
import edu.msu.prl.PhenomicsControl.Commons.timeline.Protocol;
import edu.msu.prl.PhenomicsControl.ControlSystem.control.cameras.CameraProtocol;
import edu.msu.prl.PhenomicsControl.ControlSystem.control.resource.fpga.*;

public class WaveformReference {
 public static void main(String[] args) throws Exception {
  Field f=Unsafe.class.getDeclaredField("theUnsafe");f.setAccessible(true);Unsafe unsafe=(Unsafe)f.get(null);
  ProtocolEngine engine=(ProtocolEngine)unsafe.allocateInstance(ProtocolEngine.class);
  FPGA_Control pins=(FPGA_Control)Proxy.newProxyInstance(FPGA_Control.class.getClassLoader(),new Class[]{FPGA_Control.class},(proxy,method,values)->{
   switch(method.getName()) {
    case "getFastSwitchPin":return 5;
    case "getAuxFastSwitchPin":return 17;
    case "getSatFlashPin":return 4;
    case "getMeasuringPulsePins":return new int[]{6,21,22,23};
    default:throw new AssertionError("Unexpected hardware/reference call: "+method.getName());
   }
  });
  Field dev=ProtocolEngine.class.getDeclaredField("fpgaControl");dev.setAccessible(true);dev.set(engine,pins);
  Method compile=ProtocolEngine.class.getDeclaredMethod("createProtocol",CameraProtocol.class,int.class,int[].class,double.class,double.class,double.class);compile.setAccessible(true);
  JsonArray inputs=new JsonParser().parse(new String(Files.readAllBytes(Paths.get(args[0])),"UTF-8")).getAsJsonArray();
  JsonArray output=new JsonArray();
  for(JsonElement item:inputs){
   JsonObject input=item.getAsJsonObject();Protocol raw=new Protocol();raw.setSensorGroupID("*");raw.getSensorIDs().add("*");
   for(Map.Entry<String,JsonElement> e:input.getAsJsonObject("fields").entrySet())raw.setField(e.getKey(),e.getValue().getAsString());
   CameraProtocol camera=new CameraProtocol(raw);
   ChrisBlasterProtocol waveform=(ChrisBlasterProtocol)compile.invoke(engine,camera,32,new int[]{7,8,9,10,11,12},0.0000025,0.035,0.035);
   JsonObject result=new JsonObject();result.add("source",input.get("source"));result.add("id",input.get("id"));result.addProperty("terminal_mask",waveform.getTerminalBitmask());result.addProperty("frame_count",camera.getFrameCount());
   JsonArray loops=new JsonArray();
   for(int i=0;i<waveform.getNumberLoops();i++){
    JsonObject loop=new JsonObject();loop.addProperty("repetitions",waveform.getNumberRepetitions(i));JsonArray pulses=new JsonArray();
    for(int j=0;j<waveform.getNumberBitmasks(i);j++){
     JsonObject pulse=new JsonObject();pulse.addProperty("bitmask",waveform.getBitmask(i,j).bitmask);pulse.addProperty("seconds",waveform.getBitmask(i,j).duration);pulses.add(pulse);
    }
    loop.add("pulses",pulses);loops.add(loop);
   }
   result.add("loops",loops);output.add(result);
  }
  Files.write(Paths.get(args[1]),new GsonBuilder().setPrettyPrinting().create().toJson(output).getBytes("UTF-8"));
  System.out.println("Reference protocols compiled without hardware: "+output.size());
 }
}
