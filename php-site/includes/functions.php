<?php
/** Общие функции-помощники. */

require_once __DIR__ . '/db.php';

/* ----------------------------- Базовое -------------------------------- */

function app_config(): array
{
    static $cfg = null;
    if ($cfg === null) {
        $cfg = require __DIR__ . '/../config.php';
    }
    return $cfg;
}

/** Экранирование для вывода в HTML. */
function e(?string $s): string
{
    return htmlspecialchars($s ?? '', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

/** Базовый URL сайта (с учётом подкаталога). */
function base_url(): string
{
    static $base = null;
    if ($base !== null) {
        return $base;
    }
    $cfg = app_config();
    if (!empty($cfg['base_url'])) {
        return $base = rtrim($cfg['base_url'], '/');
    }
    $https  = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off')
        || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https');
    $scheme = $https ? 'https' : 'http';
    $host   = $_SERVER['HTTP_HOST'] ?? 'localhost';

    // Веб-путь к корню приложения (= каталог, где лежит index.php),
    // вычисляется относительно DOCUMENT_ROOT — корректно и в подпапке, и в /admin.
    $rel     = '';
    $appRoot = realpath(dirname(__DIR__));
    $docRoot = realpath($_SERVER['DOCUMENT_ROOT'] ?? '');
    if ($appRoot && $docRoot && str_starts_with($appRoot, $docRoot)) {
        $rel = str_replace('\\', '/', substr($appRoot, strlen($docRoot)));
    } else {
        // Запасной вариант: каталог текущего скрипта (без /admin).
        $dir = rtrim(str_replace('\\', '/', dirname($_SERVER['SCRIPT_NAME'] ?? '/')), '/');
        $dir = preg_replace('#/admin$#', '', $dir);
        $rel = $dir;
    }
    $rel = '/' . trim($rel, '/');
    if ($rel === '/') {
        $rel = '';
    }
    return $base = $scheme . '://' . $host . $rel;
}

/** Ссылка на публичную страницу (ЧПУ). */
function url(string $path = ''): string
{
    $path = ltrim($path, '/');
    return base_url() . '/' . $path;
}

/** Ссылка на статический ресурс / загруженный файл. */
function asset(string $path): string
{
    if ($path === '') {
        return '';
    }
    if (preg_match('#^https?://#', $path)) {
        return $path;
    }
    return base_url() . '/' . ltrim($path, '/');
}

function admin_url(string $page = '', array $params = []): string
{
    $q = array_merge($page !== '' ? ['p' => $page] : [], $params);
    return base_url() . '/admin/' . ($q ? '?' . http_build_query($q) : '');
}

function redirect(string $to): void
{
    header('Location: ' . $to);
    exit;
}

function format_price(int $n): string
{
    return number_format($n, 0, '.', ' ');
}

function now(): string
{
    return date('Y-m-d H:i:s');
}

/* ----------------------------- Настройки ------------------------------ */

function all_settings(): array
{
    static $s = null;
    if ($s === null) {
        $s = [];
        foreach (db()->query('SELECT skey, svalue FROM settings')->fetchAll() as $row) {
            $s[$row['skey']] = $row['svalue'];
        }
    }
    return $s;
}

function setting(string $key, string $default = ''): string
{
    $s = all_settings();
    return array_key_exists($key, $s) ? (string) $s[$key] : $default;
}

function set_setting(string $key, string $value): void
{
    $driver = db_driver(db());
    if ($driver === 'mysql') {
        $sql = 'INSERT INTO settings (skey, svalue) VALUES (?, ?) ON DUPLICATE KEY UPDATE svalue = VALUES(svalue)';
    } else {
        $sql = 'INSERT INTO settings (skey, svalue) VALUES (?, ?) ON CONFLICT(skey) DO UPDATE SET svalue = excluded.svalue';
    }
    db()->prepare($sql)->execute([$key, $value]);
}

/* -------------------------- Текстовые блоки --------------------------- */

function blocks_for(string $page): array
{
    $out = [];
    $st = db()->prepare('SELECT bkey, bvalue FROM content_blocks WHERE page = ? ORDER BY sort ASC');
    $st->execute([$page]);
    foreach ($st->fetchAll() as $row) {
        $out[$row['bkey']] = $row['bvalue'];
    }
    // Подстраховка: если блоков нет (например, добавили новый ключ) — берём дефолты.
    require_once __DIR__ . '/blocks.php';
    $defaults = block_defaults()[$page] ?? [];
    foreach ($defaults as $k => $def) {
        if (!array_key_exists($k, $out)) {
            $out[$k] = $def['value'];
        }
    }
    return $out;
}

/* ----------------------------- Соцсети -------------------------------- */

function social_links(): array
{
    $links = [];
    $add = function (string $key, string $label, ?string $href) use (&$links) {
        if ($href) {
            $links[] = ['key' => $key, 'label' => $label, 'href' => $href];
        }
    };
    $add('vk', 'ВКонтакте', setting('vk') ?: null);
    $tg = setting('telegram');
    if ($tg) {
        $add('telegram', 'Telegram', str_starts_with($tg, 'http') ? $tg : 'https://t.me/' . ltrim($tg, '@'));
    }
    $wa = setting('whatsapp');
    if ($wa) {
        $add('whatsapp', 'WhatsApp', str_starts_with($wa, 'http') ? $wa : 'https://wa.me/' . preg_replace('/\D/', '', $wa));
    }
    $add('instagram', 'Instagram', setting('instagram') ?: null);
    $add('youtube', 'YouTube', setting('youtube') ?: null);
    $add('yandex', 'Яндекс Карты', setting('yandex_maps') ?: null);
    return $links;
}

function tel_href(string $phone): string
{
    return 'tel:' . preg_replace('/[^0-9+]/', '', $phone);
}

/* ------------------------------ Загрузка ------------------------------ */

function upload_image(string $field): string
{
    if (empty($_FILES[$field]) || ($_FILES[$field]['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK) {
        return '';
    }
    $allowed = [
        'image/jpeg' => 'jpg', 'image/png' => 'png', 'image/webp' => 'webp',
        'image/gif' => 'gif', 'image/svg+xml' => 'svg',
    ];
    $tmp  = $_FILES[$field]['tmp_name'];
    $info = @getimagesize($tmp);
    $mime = $_FILES[$field]['type'];
    if (function_exists('finfo_open')) {
        $f = finfo_open(FILEINFO_MIME_TYPE);
        $mime = finfo_file($f, $tmp) ?: $mime;
        finfo_close($f);
    }
    if (!isset($allowed[$mime])) {
        return '';
    }
    $ext = $allowed[$mime];
    $dir = __DIR__ . '/../uploads';
    if (!is_dir($dir)) {
        @mkdir($dir, 0775, true);
    }
    $name = bin2hex(random_bytes(8)) . '.' . $ext;
    if (!move_uploaded_file($tmp, $dir . '/' . $name)) {
        // На случай тестовой среды (PHP built-in server без upload).
        return '';
    }
    return 'uploads/' . $name;
}

/* ------------------------------- Прочее ------------------------------- */

function slugify(string $s): string
{
    $map = [
        'а'=>'a','б'=>'b','в'=>'v','г'=>'g','д'=>'d','е'=>'e','ё'=>'e','ж'=>'zh','з'=>'z',
        'и'=>'i','й'=>'y','к'=>'k','л'=>'l','м'=>'m','н'=>'n','о'=>'o','п'=>'p','р'=>'r',
        'с'=>'s','т'=>'t','у'=>'u','ф'=>'f','х'=>'h','ц'=>'c','ч'=>'ch','ш'=>'sh','щ'=>'sch',
        'ъ'=>'','ы'=>'y','ь'=>'','э'=>'e','ю'=>'yu','я'=>'ya',
    ];
    $s = mb_strtolower($s, 'UTF-8');
    $s = strtr($s, $map);
    $s = preg_replace('/[^a-z0-9]+/', '-', $s);
    $s = trim($s, '-');
    return $s !== '' ? substr($s, 0, 80) : 'item-' . time();
}

function format_date_ru(string $datetime): string
{
    $months = [1=>'января',2=>'февраля',3=>'марта',4=>'апреля',5=>'мая',6=>'июня',
        7=>'июля',8=>'августа',9=>'сентября',10=>'октября',11=>'ноября',12=>'декабря'];
    $ts = strtotime($datetime) ?: time();
    return (int) date('j', $ts) . ' ' . $months[(int) date('n', $ts)] . ' ' . date('Y', $ts);
}

/** Иконка соцсети (inline SVG). */
function social_icon_svg(string $key): string
{
    $i = [
        'vk' => '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12.8 16.3c-5.3 0-8.6-3.7-8.7-9.8h2.7c.1 4.5 2.1 6.3 3.6 6.7V6.5h2.5v3.8c1.5-.2 3-1.8 3.6-3.8h2.5c-.4 2.4-2 4-3.2 4.7 1.2.6 3 2 3.7 4.6h-2.8c-.5-1.7-1.9-3-3.8-3.2v3.2h-.3Z"/></svg>',
        'telegram' => '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M21.9 4.3 18.7 19c-.2 1-.9 1.3-1.8.8l-4.8-3.6-2.3 2.2c-.3.3-.5.5-1 .5l.3-4.9 8.9-8c.4-.3-.1-.5-.6-.2L6.5 13.1l-4.7-1.5c-1-.3-1-1 .2-1.5l18.4-7.1c.9-.3 1.6.2 1.5 1.3Z"/></svg>',
        'whatsapp' => '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 0 0-8.5 15.2L2 22l4.9-1.4A10 10 0 1 0 12 2Zm0 18a8 8 0 0 1-4.1-1.1l-.3-.2-2.9.8.8-2.8-.2-.3A8 8 0 1 1 12 20Zm4.4-5.6c-.2-.1-1.4-.7-1.7-.8-.2-.1-.4-.1-.5.1l-.7.9c-.1.2-.3.2-.5.1a6.5 6.5 0 0 1-3.2-2.8c-.2-.4.2-.4.6-1.2.1-.1 0-.3 0-.4l-.8-1.9c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3c-.3.3-.9.9-.9 2.1s.9 2.5 1 2.6c.1.2 1.8 2.8 4.4 3.9 1.6.7 2.3.7 3.1.6.5-.1 1.4-.6 1.6-1.1.2-.6.2-1 .1-1.1l-.1-.1Z"/></svg>',
        'instagram' => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.2" cy="6.8" r="1" fill="currentColor" stroke="none"/></svg>',
        'youtube' => '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M22 8.2a3 3 0 0 0-2.1-2.1C18 5.5 12 5.5 12 5.5s-6 0-7.9.6A3 3 0 0 0 2 8.2 31 31 0 0 0 1.7 12 31 31 0 0 0 2 15.8a3 3 0 0 0 2.1 2.1c1.9.6 7.9.6 7.9.6s6 0 7.9-.6a3 3 0 0 0 2.1-2.1c.3-1.9.3-3.8.3-3.8s0-1.9-.3-3.8ZM10 15V9l5.2 3-5.2 3Z"/></svg>',
        'yandex' => '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M13.3 3h2.4v18h-2.4v-7.3h-1L8.1 21H5.4l3.6-7.8C7.3 12.4 6 11 6 8.4 6 5.2 8 3 11 3h2.3Zm0 2H11c-1.6 0-2.6 1.3-2.6 3.4 0 2 1 3.2 2.7 3.2h2.2V5Z"/></svg>',
    ];
    return $i[$key] ?? $i['yandex'];
}

/** Иконка услуги (inline SVG). */
function service_icon(string $name): string
{
    $icons = [
        'user'     => '<circle cx="12" cy="8" r="4"/><path d="M4 20c0-3.3 3.6-6 8-6s8 2.7 8 6"/>',
        'users'    => '<circle cx="9" cy="8" r="3.2"/><path d="M2.5 20c0-3 3-5.2 6.5-5.2s6.5 2.2 6.5 5.2"/><path d="M16 5.5a3 3 0 0 1 0 5.8M17.5 14.6c2.4.6 4 2.4 4 5.4"/>',
        'palette'  => '<path d="M12 3a9 9 0 1 0 0 18c1.7 0 2-1.3 1.2-2.2-.8-.9-.5-2.3.9-2.3H17a4 4 0 0 0 4-4c0-4.7-4-9.5-9-9.5Z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7" r="1"/><circle cx="14.5" cy="7.5" r="1"/>',
        'sparkles' => '<path d="M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3Z"/><path d="M18 14l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8.8-2Z"/>',
        'video'    => '<rect x="2.5" y="6" width="13" height="12" rx="2"/><path d="M15.5 10l6-3v10l-6-3"/>',
        'heart'    => '<path d="M12 20s-7-4.4-9.2-9C1.4 8 2.8 4.8 6 4.8c2 0 3.2 1.2 4 2.4.8-1.2 2-2.4 4-2.4 3.2 0 4.6 3.2 3.2 6.2C19 15.6 12 20 12 20Z"/>',
    ];
    $body = $icons[$name] ?? $icons['heart'];
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' . $body . '</svg>';
}
