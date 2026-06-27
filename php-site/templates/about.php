<?php /** @var array $blocks $education $diplomas */ ?>
<section class="section">
    <div class="container">
        <div class="about-grid">
            <aside class="about-aside">
                <div class="about-photo">
                    <?php $photo = setting('about_photo') ?: setting('hero_photo'); ?>
                    <?php if ($photo): ?>
                        <img src="<?= e(asset($photo)) ?>" alt="<?= e(setting('owner_name')) ?>">
                    <?php else: ?>
                        <div class="portrait-placeholder">Н·Ч</div>
                    <?php endif; ?>
                </div>
                <div class="about-card">
                    <strong><?= e(setting('owner_name')) ?></strong>
                    <span><?= e(setting('profession')) ?></span>
                </div>
            </aside>
            <div>
                <h1><?= e($blocks['title']) ?></h1>
                <p class="lead"><?= e($blocks['lead']) ?></p>
                <div class="prose">
                    <?php foreach (preg_split('/\n\s*\n/', $blocks['body']) as $p): ?>
                        <?php if (trim($p) !== ''): ?><p><?= e(trim($p)) ?></p><?php endif; ?>
                    <?php endforeach; ?>
                </div>
            </div>
        </div>

        <div class="about-section">
            <h2><?= e($blocks['edu_title']) ?></h2>
            <ol class="timeline">
                <?php foreach ($education as $ed): ?>
                    <li>
                        <h3><?= e($ed['title']) ?></h3>
                        <p class="timeline-meta"><?= e(trim($ed['institution'] . ($ed['year'] ? ' · ' . $ed['year'] : ''), ' ·')) ?></p>
                        <?php if ($ed['description']): ?><p><?= e($ed['description']) ?></p><?php endif; ?>
                    </li>
                <?php endforeach; ?>
            </ol>
        </div>

        <div class="about-section">
            <h2><?= e($blocks['diplomas_title']) ?></h2>
            <p class="muted"><?= e($blocks['diplomas_hint']) ?></p>
            <?php require __DIR__ . '/partials/diploma_gallery.php'; ?>
        </div>
    </div>
</section>
