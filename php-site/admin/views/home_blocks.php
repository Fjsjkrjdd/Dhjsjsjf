<?php /** @var array $items; @var array $types */ ?>
<div class="admin-head">
    <div><h1>Блоки главной страницы</h1><p>Включайте, отключайте, меняйте порядок и добавляйте произвольные секции.</p></div>
    <a href="<?= e(admin_url('content', ['page' => 'home'])) ?>" class="btn btn-outline btn-sm">Редактировать тексты</a>
</div>

<form method="post" action="<?= e(admin_url('home-blocks')) ?>" class="adm-card">
    <?= csrf_field() ?>
    <input type="hidden" name="action" value="add">
    <h2>Добавить блок</h2>
    <div class="adm-grid cols-3">
        <div class="adm-field"><label>Тип блока</label>
            <select name="section_type" required>
                <?php foreach ($types as $k => $l): ?>
                    <option value="<?= e($k) ?>"><?= e($l) ?></option>
                <?php endforeach; ?>
            </select>
        </div>
        <div class="adm-field"><label>Заголовок (необязательно)</label><input name="title" placeholder="Переопределяет стандартный"></div>
        <div class="adm-field"><label>Порядок</label><input type="number" name="sort" value="<?= count($items) ?>"></div>
    </div>
    <div class="adm-field"><label>Подзаголовок / текст (для произвольного блока — HTML)</label><textarea name="body" rows="3" placeholder="Для типа «Произвольный блок» можно вставить HTML"></textarea></div>
    <button class="btn btn-primary btn-sm">Добавить на главную</button>
</form>

<?php foreach ($items as $item):
    $typeLabel = $types[$item['section_type']] ?? $item['section_type'];
?>
<div class="adm-list-item <?= $item['is_active'] ? '' : 'adm-section-off' ?>">
    <div>
        <strong><?= e($typeLabel) ?></strong>
        <?php if (!$item['is_active']): ?><span class="adm-tag">скрыт</span><?php endif; ?>
        <?php if ($item['title']): ?><div class="muted" style="font-size:.85rem"><?= e($item['title']) ?></div><?php endif; ?>
        <div class="muted" style="font-size:.78rem">Порядок: <?= (int) $item['sort'] ?></div>
    </div>
    <div class="adm-actions">
        <form method="post" action="<?= e(admin_url('home-blocks')) ?>" class="adm-sort-btns">
            <?= csrf_field() ?>
            <input type="hidden" name="action" value="move">
            <input type="hidden" name="id" value="<?= (int) $item['id'] ?>">
            <button type="submit" name="dir" value="up" title="Выше">↑</button>
            <button type="submit" name="dir" value="down" title="Ниже">↓</button>
        </form>
        <form method="post" action="<?= e(admin_url('home-blocks')) ?>">
            <?= csrf_field() ?>
            <input type="hidden" name="action" value="toggle">
            <input type="hidden" name="id" value="<?= (int) $item['id'] ?>">
            <button class="btn btn-outline btn-sm"><?= $item['is_active'] ? 'Скрыть' : 'Показать' ?></button>
        </form>
        <?php if ($item['section_type'] === 'custom'): ?>
            <form method="post" action="<?= e(admin_url('home-blocks')) ?>" onsubmit="return confirm('Удалить блок?')">
                <?= csrf_field() ?>
                <input type="hidden" name="action" value="delete">
                <input type="hidden" name="id" value="<?= (int) $item['id'] ?>">
                <button class="btn-danger">Удалить</button>
            </form>
        <?php endif; ?>
    </div>
</div>
<?php endforeach; ?>

<?php if (!$items): ?>
    <div class="adm-card">Блоки ещё не созданы. Они появятся автоматически при первом открытии этой страницы.</div>
<?php endif; ?>
