<?php
/**
 * Конфигурация сайта.
 *
 * По умолчанию используется база SQLite (файл data/site.sqlite) — сайт работает
 * сразу после загрузки на хостинг, без создания базы данных.
 *
 * Если хотите использовать MySQL (есть на SpaceWeb), задайте 'driver' => 'mysql'
 * и заполните данные подключения из панели хостинга.
 */

return [
    // 'sqlite' (по умолчанию, ничего настраивать не нужно) или 'mysql'
    'db_driver' => 'sqlite',

    // Настройки SQLite
    'sqlite_path' => __DIR__ . '/data/site.sqlite',

    // Настройки MySQL (используются только при db_driver = 'mysql')
    'mysql' => [
        'host'    => 'localhost',
        'name'    => '',
        'user'    => '',
        'pass'    => '',
        'charset' => 'utf8mb4',
    ],

    // Секрет для подписи сессий/токенов. ОБЯЗАТЕЛЬНО смените на длинную случайную строку.
    'app_secret' => 'CHANGE-ME-please-to-a-long-random-string-32+chars',

    // Базовый URL сайта. Оставьте пустым для автоопределения.
    'base_url' => '',

    // Часовой пояс
    'timezone' => 'Europe/Moscow',
];
