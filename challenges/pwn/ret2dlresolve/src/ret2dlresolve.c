/* ret2dlresolve：无 PIE、Partial RELRO、无 Canary、无 libc 泄露。
   只能做 ret2dlresolve 才能拿到 system("/bin/sh")。 */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(void) {
    char buf[64];
    setvbuf(stdin, NULL, _IONBF, 0);
    setvbuf(stdout, NULL, _IONBF, 0);
    puts("=== dlresolve ===");
    printf("data> ");
    read(0, buf, 0x400);
    puts("bye");
    return 0;
}
