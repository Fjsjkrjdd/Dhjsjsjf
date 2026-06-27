<?php /** @var array $blocks $services; @var string $selected; @var bool $payments_enabled */ ?>
<section class="section">
    <div class="container">
        <h1><?= e($blocks['title']) ?></h1>
        <p class="lead"><?= e($blocks['subtitle']) ?></p>

        <?php if ($msg = flash()): ?>
            <div class="alert"><?= e($msg) ?></div>
        <?php endif; ?>

        <div class="booking-grid">
            <form class="card booking-form" method="post" action="<?= e(url('booking/submit')) ?>" data-booking>
                <label class="field">
                    <span>Услуга</span>
                    <select name="service" data-service-select>
                        <?php foreach ($services as $s): ?>
                            <option value="<?= e($s['slug']) ?>" data-price="<?= (int) $s['price'] ?>"
                                <?= $s['slug'] === $selected ? 'selected' : '' ?>>
                                <?= e($s['title']) ?><?= $s['price'] ? ' — ' . format_price((int) $s['price']) . ' ₽' : '' ?><?= $s['duration'] ? ' (' . e($s['duration']) . ')' : '' ?>
                            </option>
                        <?php endforeach; ?>
                    </select>
                </label>
                <div class="field-row">
                    <label class="field"><span>Ваше имя *</span><input type="text" name="name" required placeholder="Имя"></label>
                    <label class="field"><span>Телефон *</span><input type="tel" name="phone" required placeholder="+7 (___) ___-__-__"></label>
                </div>
                <div class="field-row">
                    <label class="field"><span>E-mail</span><input type="email" name="email" placeholder="email@example.com"></label>
                    <label class="field"><span>Удобная дата / время</span><input type="text" name="preferred_date" placeholder="Например, будни после 18:00"></label>
                </div>
                <label class="field"><span>Комментарий</span><textarea name="comment" rows="3" placeholder="Кратко опишите ваш запрос (по желанию)"></textarea></label>

                <?php if ($payments_enabled): ?>
                    <label class="check-box">
                        <input type="checkbox" name="pay" value="1" data-pay-toggle>
                        <span>Оплатить онлайн картой (<span data-pay-amount><?= $services ? format_price((int) $services[0]['price']) : '0' ?></span> ₽). Вы будете перенаправлены на защищённую страницу оплаты, чек придёт на e-mail.</span>
                    </label>
                <?php endif; ?>

                <label class="check-box">
                    <input type="checkbox" name="agree" value="1" required>
                    <span>Я согласен(а) на обработку персональных данных в соответствии с <a href="<?= e(url('privacy')) ?>">политикой конфиденциальности</a>.</span>
                </label>

                <button type="submit" class="btn btn-primary btn-block">Отправить заявку</button>
            </form>

            <aside class="booking-aside">
                <div class="card">
                    <h2>Контакты</h2>
                    <ul class="contact-list small">
                        <li><a href="<?= e(tel_href(setting('phone'))) ?>"><?= e(setting('phone')) ?></a></li>
                        <li><?= e(setting('address')) ?></li>
                        <li><?= e(setting('working_hours')) ?></li>
                    </ul>
                </div>
                <div class="card benefits">
                    <ul>
                        <li><?= e($blocks['benefit_1']) ?></li>
                        <li><?= e($blocks['benefit_2']) ?></li>
                        <li><?= e($blocks['benefit_3']) ?></li>
                    </ul>
                </div>
            </aside>
        </div>
    </div>
</section>
