<?php /** @var array $blocks */ ?>
<section class="section">
    <div class="container">
        <h1><?= e($blocks['title']) ?></h1>
        <p class="lead"><?= e($blocks['subtitle']) ?></p>

        <div class="contacts-grid">
            <div>
                <div class="card contact-card">
                    <ul class="contact-list">
                        <li><span class="contact-label">Телефон</span><a href="<?= e(tel_href(setting('phone'))) ?>" class="contact-value"><?= e(setting('phone')) ?></a></li>
                        <li><span class="contact-label">Адрес</span><span class="contact-value"><?= e(setting('address')) ?></span></li>
                        <li><span class="contact-label">Время работы</span><span class="contact-value"><?= e(setting('working_hours')) ?></span></li>
                        <?php if (setting('email')): ?><li><span class="contact-label">E-mail</span><a href="mailto:<?= e(setting('email')) ?>" class="contact-value"><?= e(setting('email')) ?></a></li><?php endif; ?>
                    </ul>
                    <?php $links = social_links(); require __DIR__ . '/partials/social_bar.php'; ?>
                </div>
                <a href="<?= e(url('booking')) ?>" class="cta-card">
                    <strong>Записаться на консультацию</strong>
                    <span>Очно или онлайн</span>
                </a>
            </div>
            <div class="map-box card">
                <?php if (setting('map_embed')): ?>
                    <?= setting('map_embed') ?>
                <?php else: ?>
                    <div class="map-stub">
                        <p><?= e(setting('address')) ?></p>
                        <?php if (setting('yandex_maps')): ?>
                            <a href="<?= e(setting('yandex_maps')) ?>" target="_blank" rel="noopener" class="btn btn-outline">Открыть на Яндекс Картах</a>
                        <?php endif; ?>
                    </div>
                <?php endif; ?>
            </div>
        </div>
    </div>
</section>
