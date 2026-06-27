<?php /** @var array $user */ ?>
<div class="admin-head"><div><h1>Мой профиль</h1><p>Данные для входа в админ-панель.</p></div></div>

<div class="adm-card">
    <p class="muted">E-mail для входа</p>
    <p style="font-size:1.2rem;font-weight:600"><?= e($user['email']) ?></p>
</div>

<form method="post" action="<?= e(admin_url('account')) ?>" class="adm-card" style="max-width:460px">
    <?= csrf_field() ?>
    <h2>Сменить пароль</h2>
    <div class="adm-field"><label>Текущий пароль</label><input type="password" name="current" required></div>
    <div class="adm-field"><label>Новый пароль</label><input type="password" name="next" required><span class="adm-hint">Минимум 6 символов</span></div>
    <button class="btn btn-primary">Обновить пароль</button>
</form>
