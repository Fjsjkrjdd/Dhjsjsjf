<?php
/** Общий макет публичных страниц. @var string $content @var string $page_title */
$title = isset($page_title) && $page_title ? $page_title . ' — ' . setting('site_name') : setting('meta_title');
$desc  = $meta_description ?? setting('meta_description');
$nav = [
    ''         => 'Главная',
    'services' => 'Услуги и цены',
    'about'    => 'Обо мне',
    'reviews'  => 'Отзывы',
    'articles' => 'Статьи',
    'contacts' => 'Контакты',
];
$cur = trim($_GET['route'] ?? '', '/');
$cur0 = explode('/', $cur)[0];
?><!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= e($title) ?></title>
    <meta name="description" content="<?= e($desc) ?>">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="<?= e(asset('assets/css/style.css')) ?>">
    <?= theme_css_tag() ?>
</head>
<body>
<header class="site-header" id="siteHeader">
    <div class="container header-inner">
        <a href="<?= e(url()) ?>" class="logo">
            <span class="logo-mark">Н</span>
            <span class="logo-text"><?= e(setting('logo_text')) ?></span>
        </a>
        <nav class="main-nav" id="mainNav">
            <?php foreach ($nav as $href => $label): ?>
                <a href="<?= e(url($href)) ?>" class="<?= ($cur0 === $href) ? 'active' : '' ?>"><?= e($label) ?></a>
            <?php endforeach; ?>
        </nav>
        <div class="header-cta">
            <a href="<?= e(tel_href(setting('phone'))) ?>" class="header-phone"><?= e(setting('phone')) ?></a>
            <a href="<?= e(url('booking')) ?>" class="btn btn-primary btn-sm">Записаться</a>
        </div>
        <button class="nav-toggle" id="navToggle" aria-label="Меню"><span></span><span></span><span></span></button>
    </div>
</header>

<main>
    <?= $content ?>
</main>

<footer class="site-footer">
    <div class="container footer-grid">
        <div>
            <p class="footer-name"><?= e(setting('owner_name')) ?></p>
            <p class="footer-prof"><?= e(setting('profession')) ?></p>
            <p class="footer-tagline"><?= e(setting('tagline')) ?></p>
            <?php $links = social_links(); require __DIR__ . '/partials/social_bar.php'; ?>
        </div>
        <div>
            <h3>Контакты</h3>
            <ul class="footer-list">
                <li><a href="<?= e(tel_href(setting('phone'))) ?>"><?= e(setting('phone')) ?></a></li>
                <li><?= e(setting('address')) ?></li>
                <li><?= e(setting('working_hours')) ?></li>
                <?php if (setting('email')): ?><li><a href="mailto:<?= e(setting('email')) ?>"><?= e(setting('email')) ?></a></li><?php endif; ?>
            </ul>
        </div>
        <div>
            <h3>Разделы</h3>
            <ul class="footer-list">
                <li><a href="<?= e(url('services')) ?>">Услуги и цены</a></li>
                <li><a href="<?= e(url('about')) ?>">Обо мне</a></li>
                <li><a href="<?= e(url('reviews')) ?>">Отзывы</a></li>
                <li><a href="<?= e(url('articles')) ?>">Статьи</a></li>
                <li><a href="<?= e(url('contacts')) ?>">Контакты</a></li>
                <li><a href="<?= e(url('booking')) ?>">Запись и оплата</a></li>
            </ul>
        </div>
    </div>
    <div class="footer-bottom container">
        <span>© <?= date('Y') ?> <?= e(setting('site_name')) ?>. Все права защищены.</span>
        <span>
            <a href="<?= e(url('privacy')) ?>">Политика конфиденциальности</a>
            · <a href="<?= e(admin_url()) ?>">Вход в админку</a>
        </span>
    </div>
</footer>

<script src="<?= e(asset('assets/js/main.js')) ?>"></script>
</body>
</html>
