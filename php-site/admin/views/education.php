<?php /** @var array $items */ ?>
<div class="admin-head"><div><h1>Образование и квалификация</h1><p>Отображается на странице «Обо мне».</p></div></div>

<form method="post" action="<?= e(admin_url('education')) ?>" class="adm-card">
    <?= csrf_field() ?>
    <h2>Добавить запись</h2>
    <div class="adm-grid cols-2">
        <div class="adm-field"><label>Название / специализация *</label><input name="title" required></div>
        <div class="adm-field"><label>Учебное заведение</label><input name="institution"></div>
    </div>
    <div class="adm-grid cols-2">
        <div class="adm-field"><label>Год</label><input name="year"></div>
        <div class="adm-field"><label>Порядок</label><input type="number" name="sort" value="<?= count($items) ?>"></div>
    </div>
    <div class="adm-field"><label>Описание</label><textarea name="description" rows="2"></textarea></div>
    <button class="btn btn-primary">Добавить</button>
</form>

<?php foreach ($items as $ed): ?>
    <form method="post" action="<?= e(admin_url('education')) ?>" class="adm-card">
        <?= csrf_field() ?><input type="hidden" name="id" value="<?= (int) $ed['id'] ?>">
        <div class="adm-grid cols-2">
            <div class="adm-field"><label>Название / специализация</label><input name="title" value="<?= e($ed['title']) ?>" required></div>
            <div class="adm-field"><label>Учебное заведение</label><input name="institution" value="<?= e($ed['institution']) ?>"></div>
        </div>
        <div class="adm-grid cols-2">
            <div class="adm-field"><label>Год</label><input name="year" value="<?= e($ed['year']) ?>"></div>
            <div class="adm-field"><label>Порядок</label><input type="number" name="sort" value="<?= (int) $ed['sort'] ?>"></div>
        </div>
        <div class="adm-field"><label>Описание</label><textarea name="description" rows="2"><?= e($ed['description']) ?></textarea></div>
        <div class="adm-actions">
            <button class="btn btn-primary btn-sm">Сохранить</button>
            <button class="btn-danger" formaction="<?= e(admin_url('education')) ?>" name="action" value="delete" onclick="return confirm('Удалить запись?')">Удалить</button>
        </div>
    </form>
<?php endforeach; ?>
