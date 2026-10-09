package demo;
public class Util {
  public static int help() { return 1; }
  public static int overloaded(int value) { return value; }
  public static int overloaded(String value) { return value.length(); }
}
