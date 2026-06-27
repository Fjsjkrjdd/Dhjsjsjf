<?php /** @var array $diplomas */ ?>
<?php if (empty($diplomas)): ?>
    <p class="empty-note">Дипломы и сертификаты пока не загружены. Добавьте их в админ-панели.</p>
<?php else: ?>
<div class="gallery" data-gallery>
    <button class="gallery-arrow gallery-prev" type="button" aria-label="Назад" data-gallery-prev>‹</button>
    <div class="gallery-track" data-gallery-track>
        <?php foreach ($diplomas as $i => $d): ?>
            <button type="button" class="gallery-item" data-gallery-item
                    data-index="<?= $i ?>"
                    data-src="<?= e(asset($d['image'])) ?>"
                    data-title="<?= e($d['title']) ?>"
                    data-desc="<?= e($d['description']) ?>">
                <img src="<?= e(asset($d['image'])) ?>" alt="<?= e($d['title']) ?>" loading="lazy">
                <span class="gallery-caption"><?= e($d['title']) ?></span>
            </button>
        <?php endforeach; ?>
    </div>
    <button class="gallery-arrow gallery-next" type="button" aria-label="Вперёд" data-gallery-next>›</button>
</div>
<?php endif; ?>
