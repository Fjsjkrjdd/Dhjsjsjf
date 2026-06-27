<?php /** @var string $page; @var array $pages $blocks */ ?>
<div class="admin-head"><div><h1>Тексты страниц</h1><p>Редактируйте заголовки и тексты на страницах сайта.</p></div></div>

<div class="adm-tabs">
    <?php foreach ($pages as $key => $label): ?>
        <a href="<?= e(admin_url('content', ['page' => $key])) ?>" class="<?= $key === $page ? 'active' : '' ?>"><?= e($label) ?></a>
    <?php endforeach; ?>
</div>

<form method="post" action="<?= e(admin_url('content')) ?>">
    <?= csrf_field() ?>
    <input type="hidden" name="page" value="<?= e($page) ?>">
    <div class="adm-card">
        <?php foreach ($blocks as $b): ?>
            <div class="adm-field">
                <label><?= e($b['label']) ?></label>
                <?php $long = mb_strlen($b['bvalue']) > 80 || preg_match('/(text|subtitle|description|body|lead|note)/', $b['bkey']); ?>
                <?php if ($long): ?>
                    <textarea name="block[<?= (int) $b['id'] ?>]" rows="3"><?= e($b['bvalue']) ?></textarea>
                <?php else: ?>
                    <input type="text" name="block[<?= (int) $b['id'] ?>]" value="<?= e($b['bvalue']) ?>">
                <?php endif; ?>
            </div>
        <?php endforeach; ?>
        <button class="btn btn-primary">Сохранить</button>
    </div>
</form>
