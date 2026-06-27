<?php /** @var array $items */ ?>
<div class="admin-head"><div><h1>Дипломы и сертификаты</h1><p>На сайте отображаются горизонтальной лентой с увеличением по клику.</p></div></div>

<form method="post" action="<?= e(admin_url('diplomas')) ?>" enctype="multipart/form-data" class="adm-card">
    <?= csrf_field() ?>
    <h2>Добавить диплом</h2>
    <div class="adm-field"><label>Изображение *</label><input type="file" name="image_file" accept="image/*" required></div>
    <div class="adm-grid cols-2">
        <div class="adm-field"><label>Подпись</label><input name="title" placeholder="Напр.: Московский институт психоанализа"></div>
        <div class="adm-field"><label>Порядок</label><input type="number" name="sort" value="<?= count($items) ?>"></div>
    </div>
    <div class="adm-field"><label>Описание (необязательно)</label><input name="description"></div>
    <button class="btn btn-primary">Загрузить</button>
</form>

<?php if ($items): ?>
    <div class="adm-diplomas">
        <?php foreach ($items as $d): ?>
            <div class="adm-diploma">
                <img src="<?= e(asset($d['image'])) ?>" alt="<?= e($d['title']) ?>">
                <p style="font-size:.85rem;font-weight:600;margin-top:.5rem"><?= e($d['title']) ?></p>
                <p class="muted" style="font-size:.75rem">Порядок: <?= (int) $d['sort'] ?></p>
                <form method="post" action="<?= e(admin_url('diplomas')) ?>" onsubmit="return confirm('Удалить диплом?')" style="margin-top:.4rem">
                    <?= csrf_field() ?><input type="hidden" name="action" value="delete"><input type="hidden" name="id" value="<?= (int) $d['id'] ?>">
                    <button class="btn-danger" style="width:100%">Удалить</button>
                </form>
            </div>
        <?php endforeach; ?>
    </div>
<?php else: ?>
    <div class="adm-card">Дипломы ещё не загружены.</div>
<?php endif; ?>
