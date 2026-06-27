<?php /** @var array $items; @var ?array $edit; @var bool $isNew */
$showForm = $edit || $isNew;
?>
<div class="admin-head">
    <div><h1>Страницы</h1><p>Отдельные страницы (например, политика конфиденциальности).</p></div>
    <?php if (!$showForm): ?><a href="<?= e(admin_url('pages', ['new' => 1])) ?>" class="btn btn-primary btn-sm">+ Новая страница</a><?php endif; ?>
</div>

<?php if ($showForm): ?>
    <form method="post" action="<?= e(admin_url('pages')) ?>" class="adm-card">
        <?= csrf_field() ?>
        <?php if ($edit): ?><input type="hidden" name="id" value="<?= (int) $edit['id'] ?>"><?php endif; ?>
        <div class="adm-grid cols-2">
            <div class="adm-field"><label>Заголовок *</label><input name="title" required value="<?= e($edit['title'] ?? '') ?>"></div>
            <div class="adm-field"><label>URL (slug)</label><input name="slug" value="<?= e($edit['slug'] ?? '') ?>"><span class="adm-hint">Напр.: privacy → /privacy</span></div>
        </div>
        <div class="adm-field"><label>Содержимое (HTML)</label><textarea name="body" rows="12"><?= e($edit['body'] ?? '') ?></textarea></div>
        <div class="adm-grid cols-2">
            <div class="adm-field"><label>SEO заголовок</label><input name="meta_title" value="<?= e($edit['meta_title'] ?? '') ?>"></div>
            <div class="adm-field"><label>SEO описание</label><input name="meta_description" value="<?= e($edit['meta_description'] ?? '') ?>"></div>
        </div>
        <label class="adm-check"><input type="checkbox" name="is_published" <?= ($edit['is_published'] ?? 1) ? 'checked' : '' ?>> Опубликована</label>
        <div class="adm-actions"><button class="btn btn-primary">Сохранить</button><a href="<?= e(admin_url('pages')) ?>" class="btn btn-outline btn-sm">Отмена</a></div>
    </form>
<?php else: ?>
    <?php foreach ($items as $pg): ?>
        <div class="adm-list-item">
            <div><strong><?= e($pg['title']) ?></strong> <div class="muted" style="font-size:.85rem">/<?= e($pg['slug']) ?><?= $pg['is_published'] ? '' : ' · черновик' ?></div></div>
            <div class="adm-actions">
                <a href="<?= e(admin_url('pages', ['id' => $pg['id']])) ?>" class="btn btn-outline btn-sm">Изменить</a>
                <form method="post" action="<?= e(admin_url('pages')) ?>" onsubmit="return confirm('Удалить страницу?')">
                    <?= csrf_field() ?><input type="hidden" name="action" value="delete"><input type="hidden" name="id" value="<?= (int) $pg['id'] ?>">
                    <button class="btn-danger">Удалить</button>
                </form>
            </div>
        </div>
    <?php endforeach; ?>
    <?php if (!$items): ?><div class="adm-card">Страницы ещё не созданы.</div><?php endif; ?>
<?php endif; ?>
