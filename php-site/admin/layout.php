<?php
/** Макет админ-панели. @var string $content @var string $title @var array $user */
$nav = [
    'dashboard' => 'Обзор',
    'content'   => 'Тексты страниц',
    'services'  => 'Услуги и цены',
    'diplomas'  => 'Дипломы',
    'education' => 'Образование',
    'reviews'   => 'Отзывы',
    'articles'  => 'Статьи',
    'pages'     => 'Страницы',
    'orders'    => 'Заявки и оплаты',
    'settings'  => 'Настройки сайта',
    'account'   => 'Мой профиль',
];
$active = $_GET['p'] ?? 'dashboard';
?><!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= e($title ?? 'Админ-панель') ?> — Админ-панель</title>
    <link rel="stylesheet" href="<?= e(asset('assets/css/style.css')) ?>">
    <link rel="stylesheet" href="<?= e(asset('assets/css/admin.css')) ?>">
</head>
<body class="admin-body">
<div class="admin-shell">
    <div class="admin-topbar">
        <span>Админ-панель</span>
        <button id="admToggle" aria-label="Меню">☰</button>
    </div>
    <aside class="admin-sidebar" id="admSidebar">
        <div class="admin-brand"><span class="logo-mark">Н</span><span>CMS</span></div>
        <nav class="admin-nav">
            <?php foreach ($nav as $key => $label): ?>
                <a href="<?= e(admin_url($key === 'dashboard' ? '' : $key)) ?>" class="<?= ($active === $key || ($active === 'dashboard' && $key === 'dashboard')) ? 'active' : '' ?>"><?= e($label) ?></a>
            <?php endforeach; ?>
        </nav>
        <div class="admin-foot">
            <a href="<?= e(url()) ?>" target="_blank">Открыть сайт ↗</a>
            <span class="admin-user"><?= e($user['name'] ?? $user['email'] ?? '') ?></span>
            <a href="<?= e(admin_url('logout')) ?>" class="admin-logout">Выйти</a>
        </div>
    </aside>
    <main class="admin-main">
        <?php if ($f = flash()): ?><div class="admin-flash"><?= e($f) ?></div><?php endif; ?>
        <?= $content ?>
    </main>
</div>
<script>
document.getElementById('admToggle').addEventListener('click',function(){
  document.getElementById('admSidebar').classList.toggle('open');
});
</script>
</body>
</html>
