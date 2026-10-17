<?php
/**
 * php_unserialize：cookie data 是 base64 的序列化对象。
 * 需要构造 Logger -> FileHandler 的 gadget 链，让 __destruct 去读 /flag。
 */
error_reporting(0);

class FileHandler {
    public $path = "/etc/hostname";
    public function handle($data) {
        return @file_get_contents($this->path);
    }
}

class Logger {
    public $handler;
    public $data;
    public function __destruct() {
        if (is_object($this->handler)) {
            echo $this->handler->handle($this->data);
        }
    }
}

header('Content-Type: text/plain; charset=utf-8');

// 白盒入口：/?source=1 返回本题源码（gadget 链需要知道类名与属性名）
if (isset($_GET['source'])) {
    highlight_file(__FILE__);
    exit;
}

$raw = $_COOKIE['data'] ?? '';
if ($raw === '') {
    echo "php_unserialize\n";
    echo "cookie: data=<base64(serialize(obj))>\n";
    echo "source: /?source=1\n";
    exit;
}
$decoded = base64_decode($raw, true);
if ($decoded === false) {
    echo "bad base64\n";
    exit;
}
$obj = @unserialize($decoded);
if ($obj === false) {
    echo "bad payload\n";
}
