#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static void init(void) {
    setvbuf(stdin, NULL, _IONBF, 0);
    setvbuf(stdout, NULL, _IONBF, 0);
}

int main(void) {
    char buf[256];
    int n;

    init();
    printf("=== fmtstr ===\n");

    printf("name> ");
    n = read(0, buf, 255);
    if (n < 0) return 1;
    if (n < 256) buf[n] = '\0';
    printf("hello, ");
    printf(buf);
    putchar('\n');

    printf("data> ");
    read(0, buf, 512);

    printf("bye\n");
    return 0;
}
