<?php /** @var string $error */ ?><!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Вход в админ-панель</title>
    <link rel="stylesheet" href="<?= e(asset('assets/css/style.css')) ?>">
    <link rel="stylesheet" href="<?= e(asset('assets/css/admin.css')) ?>">
</head>
<body class="admin-body">
<div class="adm-login">
    <div class="section-center" style="margin-bottom:1.5rem">
        <span class="logo-mark" style="margin:0 auto">Н</span>
        <h1 style="margin-top:1rem">Админ-панель</h1>
        <p class="muted">Управление сайтом психолога</p>
    </div>
    <form method="post" action="<?= e(admin_url('login')) ?>" class="adm-card">
        <?= csrf_field() ?>
        <div class="adm-field">
            <label>E-mail</label>
            <input type="email" name="email" required autocomplete="username" placeholder="admin@chernova-psy.ru">
        </div>
        <div class="adm-field">
            <label>Пароль</label>
            <input type="password" name="password" required autocomplete="current-password" placeholder="••••••••">
        </div>
        <?php if (!empty($error)): ?><p style="color:var(--terracotta-dark);font-weight:600;margin-bottom:1rem"><?= e($error) ?></p><?php endif; ?>
        <button type="submit" class="btn btn-primary btn-block">Войти</button>
    </form>
    <p class="section-center muted" style="margin-top:1rem"><a href="<?= e(url()) ?>">← На сайт</a></p>
</div>
</body>
</html>
