<?php /** @var array $blocks $services $section */ ?>
<section class="section section-alt" id="services">
    <div class="container">
        <div class="section-head">
            <h2><?= e($section['title'] ?: $blocks['services_title']) ?></h2>
            <p><?= e($section['subtitle'] ?: $blocks['services_subtitle']) ?></p>
        </div>
        <div class="cards-grid">
            <?php foreach ($services as $s): ?>
                <?php require __DIR__ . '/../service_card.php'; ?>
            <?php endforeach; ?>
        </div>
        <div class="section-center" style="margin-top:2rem">
            <a href="<?= e(url('services')) ?>" class="link-arrow">Подробнее об услугах →</a>
        </div>
    </div>
</section>
