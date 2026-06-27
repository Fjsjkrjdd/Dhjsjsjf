<?php
/** @var array $links @var string $class */
$class = $class ?? '';
if (!empty($links)): ?>
<div class="social-bar <?= e($class) ?>">
    <?php foreach ($links as $l): ?>
        <a href="<?= e($l['href']) ?>" target="_blank" rel="noopener" aria-label="<?= e($l['label']) ?>" title="<?= e($l['label']) ?>">
            <?= social_icon_svg($l['key']) ?>
        </a>
    <?php endforeach; ?>
</div>
<?php endif; ?>
