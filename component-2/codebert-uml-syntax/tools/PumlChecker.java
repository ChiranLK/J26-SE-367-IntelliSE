import java.nio.file.*;
import java.io.*;
import java.util.*;
import net.sourceforge.plantuml.*;
import net.sourceforge.plantuml.core.Diagram;
import net.sourceforge.plantuml.error.PSystemError;

// Reads one file path per line on stdin, prints: path \t VALID|ERROR \t line \t message
public class PumlChecker {
  public static void main(String[] a) throws Exception {
    BufferedReader in = new BufferedReader(new InputStreamReader(System.in));
    String p;
    while ((p = in.readLine()) != null) {
      p = p.trim(); if (p.isEmpty()) continue;
      String status = "VALID", line = "-1", msg = "";
      try {
        String src = Files.readString(Path.of(p));
        List<BlockUml> blocks = new SourceStringReader(src).getBlocks();
        if (blocks.isEmpty()) { status = "ERROR"; msg = "No @startuml block found"; }
        else {
          Diagram d = blocks.get(0).getDiagram();
          if (d instanceof PSystemError) {
            PSystemError e = (PSystemError) d;
            status = "ERROR";
            try { line = String.valueOf(e.getLineLocation().getPosition() + 1); } catch (Exception ex) {}
            StringBuilder sb = new StringBuilder();
            try { for (Object eu : e.getErrorsUml()) { sb.append(((net.sourceforge.plantuml.ErrorUml) eu).getError()).append("; "); } } catch (Throwable ex) {}
            msg = sb.length() > 0 ? sb.toString() : d.getDescription().getDescription();
          }
        }
      } catch (Throwable t) { status = "ERROR"; msg = "Exception: " + t; }
      System.out.println(p + "\t" + status + "\t" + line + "\t" + msg.replace('\t',' ').replace('\n',' '));
      System.out.flush();
    }
  }
}
