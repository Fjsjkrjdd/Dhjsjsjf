<?php /** @var int $services $diplomas $reviews $articles $new_orders $paid_orders */ ?>
<div class="admin-head"><div><h1>Добро пожаловать!</h1><p>Здесь вы управляете всем содержимым сайта.</p></div></div>

<div class="adm-stats">
    <a class="adm-stat" href="<?= e(admin_url('services')) ?>"><div class="num"><?= $services ?></div><div class="lbl">Услуги</div></a>
    <a class="adm-stat" href="<?= e(admin_url('diplomas')) ?>"><div class="num"><?= $diplomas ?></div><div class="lbl">Дипломы</div></a>
    <a class="adm-stat" href="<?= e(admin_url('reviews')) ?>"><div class="num"><?= $reviews ?></div><div class="lbl">Отзывы</div></a>
    <a class="adm-stat" href="<?= e(admin_url('articles')) ?>"><div class="num"><?= $articles ?></div><div class="lbl">Статьи</div></a>
    <a class="adm-stat" href="<?= e(admin_url('orders')) ?>"><div class="num"><?= $new_orders ?></div><div class="lbl">Новые заявки</div></a>
    <a class="adm-stat" href="<?= e(admin_url('orders')) ?>"><div class="num"><?= $paid_orders ?></div><div class="lbl">Оплачено</div></a>
</div>

<div class="adm-grid cols-2">
    <div class="adm-card">
        <h2>Онлайн-касса</h2>
        <p class="muted"><?= payments_configured()
            ? 'Онлайн-оплата настроена и активна. Клиенты могут оплачивать консультации на сайте.'
            : 'Онлайн-оплата ещё не настроена. Укажите данные ЮKassa в настройках, чтобы принимать платежи и формировать чеки (54-ФЗ).' ?></p>
        <p style="margin-top:.8rem"><a href="<?= e(admin_url('settings')) ?>" class="link-arrow">Перейти к настройкам оплаты →</a></p>
    </div>
    <div class="adm-card">
        <h2>Быстрые действия</h2>
        <ul style="list-style:none;display:flex;flex-direction:column;gap:.5rem">
            <li><a class="link-arrow" href="<?= e(admin_url('content', ['page' => 'home'])) ?>">Изменить тексты на главной</a></li>
            <li><a class="link-arrow" href="<?= e(admin_url('diplomas')) ?>">Загрузить дипломы</a></li>
            <li><a class="link-arrow" href="<?= e(admin_url('services')) ?>">Обновить услуги и цены</a></li>
            <li><a class="link-arrow" href="<?= e(admin_url('settings')) ?>">Контакты и соцсети</a></li>
        </ul>
    </div>
</div>
