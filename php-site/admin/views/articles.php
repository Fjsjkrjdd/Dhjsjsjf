<?php /** @var array $items; @var ?array $edit; @var bool $isNew */
$showForm = $edit || $isNew;
?>
<div class="admin-head">
    <div><h1>Статьи</h1><p>Блог и полезные материалы.</p></div>
    <?php if (!$showForm): ?><a href="<?= e(admin_url('articles', ['new' => 1])) ?>" class="btn btn-primary btn-sm">+ Новая статья</a><?php endif; ?>
</div>

<?php if ($showForm): ?>
    <form method="post" action="<?= e(admin_url('articles')) ?>" enctype="multipart/form-data" class="adm-card">
        <?= csrf_field() ?>
        <?php if ($edit): ?><input type="hidden" name="id" value="<?= (int) $edit['id'] ?>"><?php endif; ?>
        <div class="adm-grid cols-2">
            <div class="adm-field"><label>Заголовок *</label><input name="title" required value="<?= e($edit['title'] ?? '') ?>"></div>
            <div class="adm-field"><label>URL (slug)</label><input name="slug" value="<?= e($edit['slug'] ?? '') ?>"></div>
        </div>
        <div class="adm-grid cols-2">
            <div class="adm-field"><label>Категория</label><input name="category" value="<?= e($edit['category'] ?? '') ?>" placeholder="Тревога, Отношения…"></div>
            <div class="adm-field">
                <label>Обложка</label>
                <?php if (!empty($edit['cover'])): ?><img src="<?= e(asset($edit['cover'])) ?>" class="adm-thumb" style="width:120px;height:70px" alt=""><?php endif; ?>
                <input type="hidden" name="cover" value="<?= e($edit['cover'] ?? '') ?>">
                <input type="file" name="cover_file" accept="image/*">
            </div>
        </div>
        <div class="adm-field"><label>Краткое описание (анонс)</label><textarea name="excerpt" rows="2"><?= e($edit['excerpt'] ?? '') ?></textarea></div>
        <div class="adm-field"><label>Текст статьи (HTML)</label><textarea name="body" rows="12"><?= e($edit['body'] ?? '') ?></textarea><span class="adm-hint">Поддерживается HTML: &lt;p&gt;, &lt;h2&gt;, &lt;ul&gt;, &lt;a&gt; и т.д.</span></div>
        <div class="adm-grid cols-2">
            <div class="adm-field"><label>SEO заголовок</label><input name="meta_title" value="<?= e($edit['meta_title'] ?? '') ?>"></div>
            <div class="adm-field"><label>SEO описание</label><input name="meta_description" value="<?= e($edit['meta_description'] ?? '') ?>"></div>
        </div>
        <label class="adm-check"><input type="checkbox" name="is_published" <?= ($edit['is_published'] ?? 1) ? 'checked' : '' ?>> Опубликована</label>
        <div class="adm-actions"><button class="btn btn-primary">Сохранить</button><a href="<?= e(admin_url('articles')) ?>" class="btn btn-outline btn-sm">Отмена</a></div>
    </form>
<?php else: ?>
    <?php foreach ($items as $a): ?>
        <div class="adm-list-item">
            <div><strong><?= e($a['title']) ?></strong> <?php if (!$a['is_published']): ?><span class="adm-tag">черновик</span><?php endif; ?>
                <?php if ($a['category']): ?><div class="muted" style="font-size:.85rem"><?= e($a['category']) ?></div><?php endif; ?></div>
            <div class="adm-actions">
                <a href="<?= e(admin_url('articles', ['id' => $a['id']])) ?>" class="btn btn-outline btn-sm">Изменить</a>
                <form method="post" action="<?= e(admin_url('articles')) ?>" onsubmit="return confirm('Удалить статью?')">
                    <?= csrf_field() ?><input type="hidden" name="action" value="delete"><input type="hidden" name="id" value="<?= (int) $a['id'] ?>">
                    <button class="btn-danger">Удалить</button>
                </form>
            </div>
        </div>
    <?php endforeach; ?>
    <?php if (!$items): ?><div class="adm-card">Статьи ещё не созданы.</div><?php endif; ?>
<?php endif; ?>
