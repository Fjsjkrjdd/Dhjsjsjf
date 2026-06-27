<?php /** @var array $items */
function rating_opts(int $val): string {
    $o = '';
    foreach ([5,4,3,2,1] as $n) { $o .= '<option value="'.$n.'"'.($n===$val?' selected':'').'>'.$n.' ★</option>'; }
    return $o;
}
?>
<div class="admin-head"><div><h1>Отзывы</h1><p>Добавляйте отзывы клиентов (с их согласия). Можно также подключить виджет Яндекса в Настройках.</p></div></div>

<form method="post" action="<?= e(admin_url('reviews')) ?>" class="adm-card">
    <?= csrf_field() ?>
    <h2>Добавить отзыв</h2>
    <div class="adm-grid cols-3">
        <div class="adm-field"><label>Автор *</label><input name="author" required></div>
        <div class="adm-field"><label>Источник</label><input name="source" placeholder="Яндекс Карты"></div>
        <div class="adm-field"><label>Оценка</label><select name="rating"><?= rating_opts(5) ?></select></div>
    </div>
    <div class="adm-field"><label>Текст отзыва</label><textarea name="body" rows="3"></textarea></div>
    <div class="adm-grid cols-2">
        <div class="adm-field"><label>Дата (текст)</label><input name="rdate" placeholder="Март 2025"></div>
        <div class="adm-field"><label>Порядок</label><input type="number" name="sort" value="<?= count($items) ?>"></div>
    </div>
    <label class="adm-check"><input type="checkbox" name="is_published" checked> Опубликован</label>
    <button class="btn btn-primary">Добавить</button>
</form>

<?php foreach ($items as $r): ?>
    <form method="post" action="<?= e(admin_url('reviews')) ?>" class="adm-card">
        <?= csrf_field() ?><input type="hidden" name="id" value="<?= (int) $r['id'] ?>">
        <div class="adm-grid cols-3">
            <div class="adm-field"><label>Автор</label><input name="author" value="<?= e($r['author']) ?>" required></div>
            <div class="adm-field"><label>Источник</label><input name="source" value="<?= e($r['source']) ?>"></div>
            <div class="adm-field"><label>Оценка</label><select name="rating"><?= rating_opts((int) $r['rating']) ?></select></div>
        </div>
        <div class="adm-field"><label>Текст отзыва</label><textarea name="body" rows="3"><?= e($r['body']) ?></textarea></div>
        <div class="adm-grid cols-2">
            <div class="adm-field"><label>Дата (текст)</label><input name="rdate" value="<?= e($r['rdate']) ?>"></div>
            <div class="adm-field"><label>Порядок</label><input type="number" name="sort" value="<?= (int) $r['sort'] ?>"></div>
        </div>
        <label class="adm-check"><input type="checkbox" name="is_published" <?= $r['is_published'] ? 'checked' : '' ?>> Опубликован</label>
        <div class="adm-actions">
            <button class="btn btn-primary btn-sm">Сохранить</button>
            <button class="btn-danger" name="action" value="delete" onclick="return confirm('Удалить отзыв?')">Удалить</button>
        </div>
    </form>
<?php endforeach; ?>
