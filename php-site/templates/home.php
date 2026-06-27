<?php /** @var array $blocks $services $diplomas $reviews */ ?>

<section class="hero">
    <div class="container hero-inner">
        <div class="hero-text">
            <span class="eyebrow"><?= e($blocks['hero_eyebrow']) ?></span>
            <h1><?= e($blocks['hero_title']) ?></h1>
            <p class="hero-sub"><?= e($blocks['hero_subtitle']) ?></p>
            <div class="hero-actions">
                <a href="<?= e(url('booking')) ?>" class="btn btn-primary">Записаться на консультацию</a>
                <a href="<?= e(tel_href(setting('phone'))) ?>" class="btn btn-outline"><?= e(setting('phone')) ?></a>
            </div>
            <?php $links = social_links(); require __DIR__ . '/partials/social_bar.php'; ?>
        </div>
        <div class="hero-photo">
            <?php if (setting('hero_photo')): ?>
                <img src="<?= e(asset(setting('hero_photo'))) ?>" alt="<?= e(setting('owner_name')) ?>">
            <?php else: ?>
                <div class="portrait-placeholder">Н·Ч</div>
            <?php endif; ?>
            <div class="hero-badge">
                <strong><?= e(setting('owner_name')) ?></strong>
                <span><?= e(setting('profession')) ?></span>
            </div>
        </div>
    </div>
    <div class="facts">
        <div class="container facts-inner">
            <div class="fact"><svg viewBox="0 0 24 24" class="ico"><path d="M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11Z" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="10" r="2.5" fill="none" stroke="currentColor" stroke-width="1.6"/></svg><span><?= e(setting('address')) ?></span></div>
            <div class="fact"><svg viewBox="0 0 24 24" class="ico"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M12 7.5V12l3 2" fill="none" stroke="currentColor" stroke-width="1.6"/></svg><span><?= e(setting('working_hours')) ?></span></div>
            <div class="fact"><svg viewBox="0 0 24 24" class="ico"><path d="M12 20s-7-4.4-9.2-9C1.4 8 2.8 4.8 6 4.8c2 0 3.2 1.2 4 2.4.8-1.2 2-2.4 4-2.4 3.2 0 4.6 3.2 3.2 6.2C19 15.6 12 20 12 20Z" fill="none" stroke="currentColor" stroke-width="1.6"/></svg><span>Конфиденциально и без осуждения</span></div>
        </div>
    </div>
</section>

<section class="section section-center narrow">
    <div class="container">
        <h2><?= e($blocks['intro_title']) ?></h2>
        <p class="lead"><?= e($blocks['intro_text']) ?></p>
    </div>
</section>

<section class="section section-alt" id="services">
    <div class="container">
        <div class="section-head">
            <h2><?= e($blocks['services_title']) ?></h2>
            <p><?= e($blocks['services_subtitle']) ?></p>
        </div>
        <div class="cards-grid">
            <?php foreach ($services as $s): ?>
                <?php require __DIR__ . '/partials/service_card.php'; ?>
            <?php endforeach; ?>
        </div>
        <div class="section-center" style="margin-top:2rem">
            <a href="<?= e(url('services')) ?>" class="link-arrow">Подробнее об услугах →</a>
        </div>
    </div>
</section>

<section class="section">
    <div class="container">
        <h2 class="section-center"><?= e($blocks['methods_title']) ?></h2>
        <div class="methods-grid">
            <?php
            $methods = [
                ['Клиническая психология', 'Профессиональная диагностика и работа с тревожными, депрессивными и невротическими состояниями.'],
                ['Системная семейная терапия', 'Помощь парам и семьям: восстановление контакта, доверия и тепла в отношениях.'],
                ['ACT — терапия принятия', 'Развитие психологической гибкости и умения жить в согласии со своими ценностями.'],
                ['Эмоционально-фокусированный подход', 'Бережная работа с эмоциями и привязанностью в паре и индивидуально.'],
            ];
            foreach ($methods as $m): ?>
                <div class="method">
                    <div class="method-ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 12.5l5 5 11-11" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
                    <h3><?= e($m[0]) ?></h3>
                    <p><?= e($m[1]) ?></p>
                </div>
            <?php endforeach; ?>
        </div>
    </div>
</section>

<section class="section section-alt">
    <div class="container">
        <div class="section-head">
            <h2><?= e($blocks['diplomas_title']) ?></h2>
            <p><?= e($blocks['diplomas_subtitle']) ?></p>
        </div>
        <?php require __DIR__ . '/partials/diploma_gallery.php'; ?>
    </div>
</section>

<section class="section">
    <div class="container">
        <h2 class="section-center"><?= e($blocks['steps_title']) ?></h2>
        <div class="steps-grid">
            <?php
            $steps = [
                ['01', 'Знакомство и запрос', 'На первой встрече знакомимся, проясняем ваш запрос и намечаем план работы.'],
                ['02', 'Бережное исследование', 'Вместе исследуем причины состояния в безопасной и поддерживающей атмосфере.'],
                ['03', 'Новые опоры', 'Осваиваем инструменты, которые помогают справляться и опираться на себя.'],
                ['04', 'Устойчивый результат', 'Закрепляем изменения, чтобы они оставались с вами в жизни.'],
            ];
            foreach ($steps as $s): ?>
                <div class="step"><span class="step-n"><?= e($s[0]) ?></span><h3><?= e($s[1]) ?></h3><p><?= e($s[2]) ?></p></div>
            <?php endforeach; ?>
        </div>
    </div>
</section>

<?php
$widget = setting('yandex_reviews_widget');
if ($widget || $reviews): ?>
<section class="section section-alt">
    <div class="container">
        <h2 class="section-center"><?= e($blocks['reviews_title']) ?></h2>
        <?php if ($widget): ?>
            <div class="yandex-widget"><?= $widget ?></div>
        <?php else: ?>
            <div class="cards-grid">
                <?php foreach ($reviews as $r): ?>
                    <?php require __DIR__ . '/partials/review_card.php'; ?>
                <?php endforeach; ?>
            </div>
            <div class="section-center" style="margin-top:2rem">
                <a href="<?= e(url('reviews')) ?>" class="link-arrow">Все отзывы →</a>
            </div>
        <?php endif; ?>
    </div>
</section>
<?php endif; ?>

<section class="cta">
    <div class="container section-center">
        <h2><?= e($blocks['cta_title']) ?></h2>
        <p><?= e($blocks['cta_text']) ?></p>
        <div class="hero-actions" style="justify-content:center">
            <a href="<?= e(url('booking')) ?>" class="btn btn-white">Записаться онлайн</a>
            <a href="<?= e(tel_href(setting('phone'))) ?>" class="btn btn-ghost-white">Позвонить: <?= e(setting('phone')) ?></a>
        </div>
    </div>
</section>
