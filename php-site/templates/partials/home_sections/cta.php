<?php /** @var array $blocks $section */ ?>
<section class="cta">
    <div class="container section-center">
        <h2><?= e($section['title'] ?: $blocks['cta_title']) ?></h2>
        <p><?= e($section['body'] ?: $blocks['cta_text']) ?></p>
        <div class="hero-actions" style="justify-content:center">
            <a href="<?= e(url('booking')) ?>" class="btn btn-white">Записаться онлайн</a>
            <?php if (payments_accepted()): ?>
                <a href="<?= e(url('booking') . '?pay=1') ?>" class="btn btn-ghost-white">Оплатить консультацию</a>
            <?php endif; ?>
            <a href="<?= e(tel_href(setting('phone'))) ?>" class="btn btn-ghost-white">Позвонить: <?= e(setting('phone')) ?></a>
        </div>
    </div>
</section>
