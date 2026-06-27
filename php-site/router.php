<?php
/**
 * Роутер ТОЛЬКО для встроенного сервера PHP (php -S) — для локального запуска/проверки.
 * На реальном хостинге (Apache) маршрутизацию выполняет .htaccess, этот файл не используется.
 *
 * Запуск:  php -S localhost:8000 router.php
 */
$uri  = urldecode(parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH));
$path = __DIR__ . $uri;

// Реальные файлы (css, js, картинки) отдаём как есть.
if ($uri !== '/' && file_exists($path) && !is_dir($path)) {
    return false;
}

// Админка.
if ($uri === '/admin' || strpos($uri, '/admin/') === 0) {
    require __DIR__ . '/admin/index.php';
    return true;
}

// Публичный сайт.
$_GET['route'] = ltrim($uri, '/');
require __DIR__ . '/index.php';
return true;
