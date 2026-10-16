#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#define MAX 16

static char *notes[MAX];
static unsigned long sizes[MAX];

static void init(void) {
    setvbuf(stdin, NULL, _IONBF, 0);
    setvbuf(stdout, NULL, _IONBF, 0);
}

static int readnum(void) {
    char b[32];
    int n = read(0, b, sizeof(b) - 1);
    if (n <= 0) exit(0);
    b[n] = '\0';
    return atoi(b);
}

static void add(void) {
    int i, s;
    printf("idx> ");
    i = readnum();
    if (i < 0 || i >= MAX) return;
    printf("size> ");
    s = readnum();
    if (s <= 0 || s > 0x500) return;
    notes[i] = malloc(s);
    if (!notes[i]) return;
    sizes[i] = s;
    printf("data> ");
    read(0, notes[i], s);
    puts("ok");
}

static void del(void) {
    int i;
    printf("idx> ");
    i = readnum();
    if (i < 0 || i >= MAX || !notes[i]) return;
    free(notes[i]);
    puts("ok");
}

static void edit(void) {
    int i;
    printf("idx> ");
    i = readnum();
    if (i < 0 || i >= MAX || !notes[i]) return;
    printf("data> ");
    read(0, notes[i], sizes[i]);
    puts("ok");
}

static void show(void) {
    int i;
    printf("idx> ");
    i = readnum();
    if (i < 0 || i >= MAX || !notes[i]) return;
    write(1, notes[i], sizes[i]);
    puts("\nok");
}

int main(void) {
    init();
    puts("=== noteheap ===");
    for (;;) {
        printf("1.add 2.del 3.edit 4.show\n> ");
        switch (readnum()) {
            case 1: add(); break;
            case 2: del(); break;
            case 3: edit(); break;
            case 4: show(); break;
            default: puts("bye"); return 0;
        }
    }
}
