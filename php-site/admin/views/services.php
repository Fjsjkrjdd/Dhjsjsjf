<?php /** @var array $items; @var ?array $edit; @var bool $isNew */
$showForm = $edit || $isNew;
$icons = ['user'=>'Человек (индивидуально)','users'=>'Пара / семья','palette'=>'Палитра (арт-терапия)','sparkles'=>'Искры (группа/игра)','video'=>'Видео (онлайн)','heart'=>'Сердце'];
?>
<div class="admin-head">
    <div><h1>Услуги и цены</h1><p>Цены, описания и порядок отображения.</p></div>
    <?php if (!$showForm): ?><a href="<?= e(admin_url('services', ['new' => 1])) ?>" class="btn btn-primary btn-sm">+ Добавить услугу</a><?php endif; ?>
</div>

<?php if ($showForm): ?>
    <form method="post" action="<?= e(admin_url('services')) ?>" enctype="multipart/form-data" class="adm-card">
        <?= csrf_field() ?>
        <?php if ($edit): ?><input type="hidden" name="id" value="<?= (int) $edit['id'] ?>"><?php endif; ?>
        <div class="adm-grid cols-2">
            <div class="adm-field"><label>Название *</label><input name="title" required value="<?= e($edit['title'] ?? '') ?>"></div>
            <div class="adm-field"><label>URL (slug)</label><input name="slug" value="<?= e($edit['slug'] ?? '') ?>"><span class="adm-hint">Пусто — сгенерируется автоматически</span></div>
        </div>
        <div class="adm-field"><label>Краткое описание</label><textarea name="short_description" rows="2"><?= e($edit['short_description'] ?? '') ?></textarea></div>
        <div class="adm-field"><label>Полное описание</label><textarea name="description" rows="5"><?= e($edit['description'] ?? '') ?></textarea></div>
        <div class="adm-grid cols-3">
            <div class="adm-field"><label>Цена, ₽</label><input type="number" name="price" value="<?= (int) ($edit['price'] ?? 0) ?>"></div>
            <div class="adm-field"><label>Старая цена, ₽</label><input type="number" name="old_price" value="<?= e((string) ($edit['old_price'] ?? '')) ?>"></div>
            <div class="adm-field"><label>Длительность</label><input name="duration" value="<?= e($edit['duration'] ?? '') ?>" placeholder="60 минут"></div>
        </div>
        <div class="adm-grid cols-2">
            <div class="adm-field"><label>Иконка</label><select name="icon"><?php foreach ($icons as $k => $l): ?><option value="<?= $k ?>" <?= ($edit['icon'] ?? 'heart') === $k ? 'selected' : '' ?>><?= e($l) ?></option><?php endforeach; ?></select></div>
            <div class="adm-field"><label>Порядок</label><input type="number" name="sort" value="<?= (int) ($edit['sort'] ?? 0) ?>"></div>
        </div>
        <div class="adm-field">
            <label>Изображения (можно выбрать несколько)</label>
            <?php
            $gallery = $edit ? service_gallery($edit) : [];
            if ($gallery): ?>
                <div class="adm-thumbs">
                    <?php foreach ($gallery as $img): ?>
                        <img src="<?= e(asset($img)) ?>" class="adm-thumb" alt="">
                    <?php endforeach; ?>
                </div>
            <?php endif; ?>
            <input type="hidden" name="image" value="<?= e($edit['image'] ?? '') ?>">
            <input type="file" name="image_file" accept="image/*">
            <input type="file" name="image_files" accept="image/*" multiple>
            <span class="adm-hint">Первое изображение — обложка карточки. Можно загрузить несколько файлов сразу.</span>
        </div>
        <label class="adm-check"><input type="checkbox" name="is_active" <?= ($edit['is_active'] ?? 1) ? 'checked' : '' ?>> Активна (показывать на сайте)</label>
        <label class="adm-check"><input type="checkbox" name="is_bookable" <?= ($edit['is_bookable'] ?? 1) ? 'checked' : '' ?>> Доступна для записи / оплаты</label>
        <div class="adm-actions"><button class="btn btn-primary">Сохранить</button><a href="<?= e(admin_url('services')) ?>" class="btn btn-outline btn-sm">Отмена</a></div>
    </form>
<?php else: ?>
    <?php foreach ($items as $s): ?>
        <div class="adm-list-item">
            <div>
                <strong><?= e($s['title']) ?></strong> <?php if (!$s['is_active']): ?><span class="adm-tag">скрыта</span><?php endif; ?>
                <div class="muted" style="font-size:.85rem"><?= format_price((int) $s['price']) ?> ₽<?= $s['duration'] ? ' · ' . e($s['duration']) : '' ?></div>
            </div>
            <div class="adm-actions">
                <a href="<?= e(admin_url('services', ['id' => $s['id']])) ?>" class="btn btn-outline btn-sm">Изменить</a>
                <form method="post" action="<?= e(admin_url('services')) ?>" onsubmit="return confirm('Удалить услугу?')">
                    <?= csrf_field() ?><input type="hidden" name="action" value="delete"><input type="hidden" name="id" value="<?= (int) $s['id'] ?>">
                    <button class="btn-danger">Удалить</button>
                </form>
            </div>
        </div>
    <?php endforeach; ?>
    <?php if (!$items): ?><div class="adm-card">Услуги ещё не добавлены.</div><?php endif; ?>
<?php endif; ?>
