<?php /** @var array $s */ ?>
<div class="price-block">
    <?php if (!empty($s['old_price']) && (int) $s['old_price'] > 0): ?>
        <span class="old-price">было <?= format_price((int) $s['old_price']) ?> ₽</span>
    <?php endif; ?>
    <span class="price-line"><span class="price"><?= format_price((int) $s['price']) ?></span><span class="price-cur"> ₽</span></span>
    <?php if (!empty($s['duration'])): ?><span class="duration"><?= e($s['duration']) ?></span><?php endif; ?>
</div>
