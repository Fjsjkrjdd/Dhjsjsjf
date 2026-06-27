<?php
/** Авторизация администратора (сессии) и защита от CSRF. */

require_once __DIR__ . '/functions.php';

function auth_boot(): void
{
    if (session_status() === PHP_SESSION_NONE) {
        $cfg = app_config();
        if (!empty($cfg['timezone'])) {
            date_default_timezone_set($cfg['timezone']);
        }
        session_name('chernova_admin');
        session_start();
    }
}

function current_user(): ?array
{
    auth_boot();
    if (empty($_SESSION['uid'])) {
        return null;
    }
    static $user = null;
    if ($user === null) {
        $st = db()->prepare('SELECT * FROM users WHERE id = ?');
        $st->execute([$_SESSION['uid']]);
        $user = $st->fetch() ?: null;
    }
    return $user;
}

function require_login(): array
{
    $u = current_user();
    if (!$u) {
        redirect(admin_url('login'));
    }
    return $u;
}

function attempt_login(string $email, string $password): bool
{
    $st = db()->prepare('SELECT * FROM users WHERE email = ?');
    $st->execute([mb_strtolower(trim($email))]);
    $user = $st->fetch();
    if (!$user || !password_verify($password, $user['password_hash'])) {
        return false;
    }
    auth_boot();
    session_regenerate_id(true);
    $_SESSION['uid'] = $user['id'];
    return true;
}

function logout(): void
{
    auth_boot();
    $_SESSION = [];
    session_destroy();
}

function csrf_token(): string
{
    auth_boot();
    if (empty($_SESSION['csrf'])) {
        $_SESSION['csrf'] = bin2hex(random_bytes(16));
    }
    return $_SESSION['csrf'];
}

function csrf_field(): string
{
    return '<input type="hidden" name="csrf" value="' . e(csrf_token()) . '">';
}

function csrf_check(): void
{
    auth_boot();
    $sent = $_POST['csrf'] ?? '';
    if (!hash_equals($_SESSION['csrf'] ?? '', $sent)) {
        http_response_code(419);
        exit('Сессия устарела. Обновите страницу и попробуйте снова.');
    }
}

function flash(string $msg = null): ?string
{
    auth_boot();
    if ($msg !== null) {
        $_SESSION['flash'] = $msg;
        return null;
    }
    $m = $_SESSION['flash'] ?? null;
    unset($_SESSION['flash']);
    return $m;
}
