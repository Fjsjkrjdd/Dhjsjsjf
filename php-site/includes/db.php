<?php
/**
 * Подключение к базе данных (PDO) и автоматическое создание таблиц.
 * Поддерживает SQLite (по умолчанию) и MySQL.
 */

function db(): PDO
{
    static $pdo = null;
    if ($pdo !== null) {
        return $pdo;
    }
    $cfg = require __DIR__ . '/../config.php';

    if (($cfg['db_driver'] ?? 'sqlite') === 'mysql') {
        $m = $cfg['mysql'];
        $dsn = "mysql:host={$m['host']};dbname={$m['name']};charset={$m['charset']}";
        $pdo = new PDO($dsn, $m['user'], $m['pass'], [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
        $pdo->driver_name = 'mysql';
    } else {
        $path = $cfg['sqlite_path'];
        $dir  = dirname($path);
        if (!is_dir($dir)) {
            @mkdir($dir, 0775, true);
        }
        $pdo = new PDO('sqlite:' . $path, null, null, [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
        $pdo->exec('PRAGMA journal_mode = WAL');
        $pdo->exec('PRAGMA foreign_keys = ON');
    }

    db_install($pdo);
    return $pdo;
}

function db_driver(PDO $pdo): string
{
    return $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
}

/** Создаёт таблицы, если их ещё нет, и наполняет стартовыми данными. */
function db_install(PDO $pdo): void
{
    $isMysql = db_driver($pdo) === 'mysql';
    $pk  = $isMysql ? 'INT AUTO_INCREMENT PRIMARY KEY' : 'INTEGER PRIMARY KEY AUTOINCREMENT';
    $eng = $isMysql ? ' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4' : '';

    $tables = [
        "CREATE TABLE IF NOT EXISTS users (
            id $pk,
            email VARCHAR(190) UNIQUE,
            password_hash VARCHAR(255),
            name VARCHAR(190),
            role VARCHAR(40)
        )$eng",
        "CREATE TABLE IF NOT EXISTS settings (
            skey VARCHAR(190) PRIMARY KEY,
            svalue TEXT
        )$eng",
        "CREATE TABLE IF NOT EXISTS content_blocks (
            id $pk,
            page VARCHAR(80),
            bkey VARCHAR(120),
            label VARCHAR(255),
            bvalue TEXT,
            sort INT DEFAULT 0
        )$eng",
        "CREATE TABLE IF NOT EXISTS services (
            id $pk,
            slug VARCHAR(190) UNIQUE,
            title VARCHAR(255),
            short_description TEXT,
            description TEXT,
            price INT DEFAULT 0,
            old_price INT,
            duration VARCHAR(120),
            icon VARCHAR(40),
            image VARCHAR(255),
            is_active INT DEFAULT 1,
            is_bookable INT DEFAULT 1,
            sort INT DEFAULT 0
        )$eng",
        "CREATE TABLE IF NOT EXISTS diplomas (
            id $pk,
            title VARCHAR(255),
            description TEXT,
            image VARCHAR(255),
            sort INT DEFAULT 0,
            is_published INT DEFAULT 1
        )$eng",
        "CREATE TABLE IF NOT EXISTS reviews (
            id $pk,
            author VARCHAR(190),
            body TEXT,
            rating INT DEFAULT 5,
            source VARCHAR(190),
            rdate VARCHAR(120),
            is_published INT DEFAULT 1,
            sort INT DEFAULT 0
        )$eng",
        "CREATE TABLE IF NOT EXISTS education (
            id $pk,
            title VARCHAR(255),
            institution VARCHAR(255),
            year VARCHAR(60),
            description TEXT,
            sort INT DEFAULT 0
        )$eng",
        "CREATE TABLE IF NOT EXISTS articles (
            id $pk,
            slug VARCHAR(190) UNIQUE,
            title VARCHAR(255),
            excerpt TEXT,
            body TEXT,
            cover VARCHAR(255),
            category VARCHAR(120),
            is_published INT DEFAULT 1,
            published_at VARCHAR(40),
            meta_title VARCHAR(255),
            meta_description TEXT
        )$eng",
        "CREATE TABLE IF NOT EXISTS pages (
            id $pk,
            slug VARCHAR(190) UNIQUE,
            title VARCHAR(255),
            body TEXT,
            meta_title VARCHAR(255),
            meta_description TEXT,
            is_published INT DEFAULT 1,
            sort INT DEFAULT 0
        )$eng",
        "CREATE TABLE IF NOT EXISTS orders (
            id $pk,
            service_id INT,
            service_title VARCHAR(255),
            customer_name VARCHAR(190),
            customer_phone VARCHAR(120),
            customer_email VARCHAR(190),
            preferred_date VARCHAR(190),
            comment TEXT,
            amount INT DEFAULT 0,
            status VARCHAR(40) DEFAULT 'new',
            payment_id VARCHAR(190),
            payment_status VARCHAR(60) DEFAULT 'pending',
            payment_url TEXT,
            receipt_status VARCHAR(40) DEFAULT 'none',
            created_at VARCHAR(40)
        )$eng",
    ];

    foreach ($tables as $sql) {
        $pdo->exec($sql);
    }

    // Признак того, что первичное наполнение уже выполнено.
    $done = $pdo->query("SELECT svalue FROM settings WHERE skey = 'installed'")->fetchColumn();
    if (!$done) {
        require __DIR__ . '/seed.php';
        db_seed($pdo);
        $pdo->prepare("INSERT INTO settings (skey, svalue) VALUES ('installed', '1')")->execute();
    }
}
