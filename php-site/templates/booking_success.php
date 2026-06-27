<?php /** @var bool $paid */ ?>
<section class="section section-center narrow">
    <div class="container">
        <div class="success-check">✓</div>
        <h1><?= $paid ? 'Оплата прошла успешно' : 'Спасибо за заявку!' ?></h1>
        <p class="lead">
            <?= $paid
                ? 'Ваша оплата получена, чек отправлен на указанный e-mail. Я свяжусь с вами для подтверждения времени встречи.'
                : 'Заявка принята. Я свяжусь с вами в ближайшее время для подтверждения записи.' ?>
        </p>
        <a href="<?= e(url()) ?>" class="btn btn-primary">Вернуться на главную</a>
    </div>
</section>
