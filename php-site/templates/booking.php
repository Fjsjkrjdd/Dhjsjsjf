<?php
/** @var array $blocks $services; @var string $selected; @var bool $payments_enabled; @var bool $payments_ready; @var bool $pay_default */
?>
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
                    <label class="field"><span>E-mail</span><input type="email" name="email" placeholder="email@example.com" <?= $pay_default ? 'required' : '' ?>></label>
                    <label class="field"><span>Удобная дата / время</span><input type="text" name="preferred_date" placeholder="Например, будни после 18:00"></label>
                </div>
                <label class="field"><span>Комментарий</span><textarea name="comment" rows="3" placeholder="Кратко опишите ваш запрос (по желанию)"></textarea></label>

                <?php if ($payments_enabled): ?>
                    <label class="check-box">
                        <input type="checkbox" name="pay" value="1" data-pay-toggle <?= $pay_default ? 'checked' : '' ?>>
                        <span>Оплатить онлайн картой (<span data-pay-amount><?= $services ? format_price((int) $services[0]['price']) : '0' ?></span> ₽). Вы будете перенаправлены на защищённую страницу оплаты<?= $payments_ready ? ', чек придёт на e-mail' : '' ?>.</span>
                    </label>
                    <?php if (!$payments_ready): ?>
                        <p class="form-hint" style="margin-top:-.4rem">Онлайн-оплата включена. Укажите shopId и секретный ключ ЮKassa в настройках (для Точка Банк — данные из личного кабинета эквайринга).</p>
                    <?php endif; ?>
                <?php endif; ?>

                <label class="check-box">
                    <input type="checkbox" name="agree" value="1" required>
                    <span>Я согласен(а) на обработку персональных данных в соответствии с <a href="<?= e(url('privacy')) ?>">политикой конфиденциальности</a>.</span>
                </label>

                <div class="booking-submit-row">
                    <button type="submit" class="btn btn-primary btn-block">Отправить заявку</button>
                    <?php if ($payments_enabled): ?>
                        <button type="submit" name="pay" value="1" class="btn btn-outline btn-block booking-pay-btn" data-pay-submit>
                            Оплатить консультацию онлайн — <span data-pay-amount-btn><?= $services ? format_price((int) $services[0]['price']) : '0' ?></span> ₽
                        </button>
                    <?php endif; ?>
                </div>
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
