int main() {
  int a = 2, b = 3;
  int c = a * b;
  int d = c * 5;
  int e = 2 * 4;
  int f = c * d * e;
  f = f * f;

  if(f != 2073600) return 1;

  unsigned int g = 5, h = g * 10;
  unsigned int i;
  h = 10 * g; // 50
  i = g * h; // 250

  if(i != 250) return 2;

  if(i / g != h) return 3;

  // Test order of operations
  if(3 + 2 * 3 != 9) return 4;

  return 0;
}