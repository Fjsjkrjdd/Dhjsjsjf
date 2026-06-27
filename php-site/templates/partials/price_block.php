<?php /** @var array $s */ ?>
<div class="price-block">
    <?php if (!empty($s['old_price']) && (int) $s['old_price'] > 0): ?>
        <span class="old-price">было <?= format_price((int) $s['old_price']) ?>&nbsp;₽</span>
    <?php endif; ?>
    <span class="price-line"><?= format_price((int) $s['price']) ?>&nbsp;₽</span>
    <?php if (!empty($s['duration'])): ?><span class="duration"><?= e($s['duration']) ?></span><?php endif; ?>
</div>
