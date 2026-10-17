/* fmt_once：单次格式化字符串（最多 31 字节）+ 第二次 read 栈溢出。
   PIE + Canary + NX + Full RELRO。 */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(void) {
    char buf[32];
    int n;

    setvbuf(stdin, NULL, _IONBF, 0);
    setvbuf(stdout, NULL, _IONBF, 0);
    puts("=== fmt_once ===");

    printf("name> ");
    n = read(0, buf, 31);
    if (n <= 0) return 1;
    buf[n] = '\0';
    printf(buf);
    putchar('\n');

    printf("data> ");
    read(0, buf, 200);
    puts("bye");
    return 0;
}
