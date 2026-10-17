/* arm_overflow：aarch64 静态链接、无 PIE、无 Canary。
   全局缓冲区溢出 → 覆盖紧邻的函数指针 handler → 调用 handler(name)。
   把 name 写成 "/bin/sh\\0"，handler 写成 system 的静态地址即可拿 shell。
   用 qemu-aarch64-static 运行，需要跨架构分析（aarch64 布局与调用约定）。 */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static char name[64];
static void (*handler)(char *) = NULL;

int main(int argc, char **argv) {
    (void)argv;
    setvbuf(stdin, NULL, _IONBF, 0);
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc == 0x3039) {           /* 不可达分支：让 system 进静态符号表 */
        system("echo unreachable");
    }
    puts("=== arm_overflow (aarch64) ===");
    printf("data> ");
    read(0, name, 0x200);
    if (handler) {
        handler(name);
    } else {
        puts("bye");
    }
    return 0;
}
