<?php /** @var array $blocks */ ?>
<section class="hero">
    <div class="container hero-inner">
        <div class="hero-text">
            <span class="eyebrow"><?= e($blocks['hero_eyebrow']) ?></span>
            <h1><?= e($blocks['hero_title']) ?></h1>
            <p class="hero-sub"><?= e($blocks['hero_subtitle']) ?></p>
            <div class="hero-actions">
                <a href="<?= e(url('booking')) ?>" class="btn btn-primary">Записаться на консультацию</a>
                <?php if (payments_accepted()): ?>
                    <a href="<?= e(url('booking') . '?pay=1') ?>" class="btn btn-outline">Оплатить консультацию онлайн</a>
                <?php endif; ?>
                <a href="<?= e(tel_href(setting('phone'))) ?>" class="btn btn-outline"><?= e(setting('phone')) ?></a>
            </div>
            <?php $links = social_links(); require __DIR__ . '/../social_bar.php'; ?>
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
