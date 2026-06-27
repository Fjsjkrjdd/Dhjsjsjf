<?php /** @var array $s */
$v = function ($k) use ($s) { return e(isset($s[$k]) ? $s[$k] : ''); };
?>
<form method="post" action="<?= e(admin_url('settings')) ?>" enctype="multipart/form-data">
    <?= csrf_field() ?>
    <div class="admin-head"><div><h1>Настройки сайта</h1><p>Контакты, соцсети, фото, SEO и онлайн-касса.</p></div><button class="btn btn-primary">Сохранить</button></div>

    <div class="adm-card">
        <h2>Основное</h2>
        <div class="adm-grid cols-2">
            <div class="adm-field"><label>Название сайта</label><input name="site_name" value="<?= $v('site_name') ?>"></div>
            <div class="adm-field"><label>Текст логотипа</label><input name="logo_text" value="<?= $v('logo_text') ?>"></div>
            <div class="adm-field"><label>Имя специалиста</label><input name="owner_name" value="<?= $v('owner_name') ?>"></div>
            <div class="adm-field"><label>Профессия / должность</label><input name="profession" value="<?= $v('profession') ?>"></div>
        </div>
        <div class="adm-field"><label>Слоган</label><textarea name="tagline" rows="2"><?= $v('tagline') ?></textarea></div>
    </div>

    <div class="adm-card">
        <h2>Фотографии</h2>
        <div class="adm-grid cols-2">
            <div class="adm-field">
                <label>Главное фото (обложка)</label>
                <?php if ($s['hero_photo'] ?? ''): ?><img src="<?= e(asset($s['hero_photo'])) ?>" class="adm-thumb" alt=""><?php endif; ?>
                <input type="hidden" name="hero_photo" value="<?= $v('hero_photo') ?>"><input type="file" name="hero_photo_file" accept="image/*" multiple>
            </div>
            <div class="adm-field">
                <label>Фото для «Обо мне»</label>
                <?php if ($s['about_photo'] ?? ''): ?><img src="<?= e(asset($s['about_photo'])) ?>" class="adm-thumb" alt=""><?php endif; ?>
                <input type="hidden" name="about_photo" value="<?= $v('about_photo') ?>"><input type="file" name="about_photo_file" accept="image/*" multiple>
            </div>
        </div>
    </div>

    <div class="adm-card">
        <h2>Контакты</h2>
        <div class="adm-grid cols-2">
            <div class="adm-field"><label>Телефон</label><input name="phone" value="<?= $v('phone') ?>"></div>
            <div class="adm-field"><label>E-mail</label><input name="email" value="<?= $v('email') ?>"></div>
            <div class="adm-field"><label>Город</label><input name="city" value="<?= $v('city') ?>"></div>
            <div class="adm-field"><label>Время работы</label><input name="working_hours" value="<?= $v('working_hours') ?>"></div>
        </div>
        <div class="adm-field"><label>Адрес</label><input name="address" value="<?= $v('address') ?>"></div>
        <div class="adm-field"><label>Карта (HTML-код виджета Яндекс.Карт)</label><textarea name="map_embed" rows="3"><?= $v('map_embed') ?></textarea><span class="adm-hint">Вставьте код &lt;iframe…&gt; из конструктора Яндекс.Карт. Пусто — покажем ссылку.</span></div>
    </div>

    <div class="adm-card">
        <h2>Социальные сети</h2>
        <div class="adm-grid cols-2">
            <div class="adm-field"><label>ВКонтакте</label><input name="vk" value="<?= $v('vk') ?>" placeholder="https://vk.com/..."></div>
            <div class="adm-field"><label>Telegram</label><input name="telegram" value="<?= $v('telegram') ?>" placeholder="@ник или ссылка"></div>
            <div class="adm-field"><label>WhatsApp</label><input name="whatsapp" value="<?= $v('whatsapp') ?>" placeholder="номер или ссылка"></div>
            <div class="adm-field"><label>Instagram</label><input name="instagram" value="<?= $v('instagram') ?>"></div>
            <div class="adm-field"><label>YouTube</label><input name="youtube" value="<?= $v('youtube') ?>"></div>
            <div class="adm-field"><label>MAX (max.ru)</label><input name="max" value="<?= $v('max') ?>" placeholder="https://max.ru/... или @ник"></div>
            <div class="adm-field"><label>Яндекс Карты</label><input name="yandex_maps" value="<?= $v('yandex_maps') ?>"></div>
        </div>
    </div>

    <div class="adm-card">
        <h2>Отзывы с Яндекс Карт (виджет)</h2>
        <div class="adm-field">
            <label>HTML-код виджета отзывов</label>
            <textarea name="yandex_reviews_widget" rows="4"><?= $v('yandex_reviews_widget') ?></textarea>
            <span class="adm-hint">Вставьте код виджета отзывов из Яндекс Бизнес / конструктора. Если заполнено — на странице «Отзывы» и на главной показывается виджет.</span>
        </div>
    </div>

    <div class="adm-card">
        <h2>SEO</h2>
        <div class="adm-field"><label>Заголовок (title)</label><input name="meta_title" value="<?= $v('meta_title') ?>"></div>
        <div class="adm-field"><label>Описание (description)</label><textarea name="meta_description" rows="2"><?= $v('meta_description') ?></textarea></div>
    </div>

    <div class="adm-card" id="themeEditor">
        <h2>Цветовая гамма сайта</h2>
        <p class="adm-hint">Выберите готовую палитру или настройте цвета вручную. Нажмите «Сохранить», чтобы применить на сайте.</p>

        <div class="theme-presets">
            <span class="lbl">Готовые палитры:</span>
            <div class="theme-preset-btns">
                <button type="button" class="btn btn-outline btn-sm" data-theme-preset="classic">Классика</button>
                <button type="button" class="btn btn-outline btn-sm" data-theme-preset="warm">Тёплая</button>
                <button type="button" class="btn btn-outline btn-sm" data-theme-preset="fresh">Свежая</button>
                <button type="button" class="btn btn-outline btn-sm" data-theme-preset="contrast">Контраст</button>
            </div>
        </div>

        <div class="theme-preview" id="themePreview">
            <span class="theme-preview-chip" data-chip="cream">Фон</span>
            <span class="theme-preview-chip" data-chip="sage">Кнопка</span>
            <span class="theme-preview-chip" data-chip="terracotta">Акцент</span>
            <span class="theme-preview-chip outline" data-chip="ink">Текст</span>
        </div>

        <?php
        $colorGroups = [
            'Фон страницы' => [
                'color_cream' => 'Основной фон',
                'color_cream_deep' => 'Фон карточек и полей',
            ],
            'Акцентные цвета' => [
                'color_sage' => 'Кнопки и ссылки',
                'color_sage_dark' => 'Кнопки при наведении',
                'color_sage_light' => 'Подсветка и фон иконок',
                'color_terracotta' => 'Звёзды отзывов',
                'color_terracotta_dark' => 'Предупреждения',
            ],
            'Текст' => [
                'color_ink' => 'Заголовки',
                'color_ink_soft' => 'Обычный текст',
            ],
        ];
        $colorDefaults = [
            'color_cream' => '#faf7f2', 'color_cream_deep' => '#f3ede3',
            'color_sage' => '#6f8f7f', 'color_sage_dark' => '#4f6f60', 'color_sage_light' => '#e7efe9',
            'color_terracotta' => '#c98a6b', 'color_terracotta_dark' => '#b5734f',
            'color_ink' => '#2c322f', 'color_ink_soft' => '#5b635e',
        ];
        foreach ($colorGroups as $groupTitle => $colors): ?>
            <h3 class="theme-group-title"><?= e($groupTitle) ?></h3>
            <div class="theme-colors">
                <?php foreach ($colors as $key => $label):
                    $def = $colorDefaults[$key] ?? '#faf7f2';
                    $val = preg_match('/^#[0-9a-fA-F]{3,8}$/', $s[$key] ?? '') ? $s[$key] : $def;
                ?>
                <div class="theme-color-row" data-color-key="<?= e($key) ?>">
                    <input type="color" class="theme-pick" name="<?= e($key) ?>" value="<?= e($val) ?>" aria-label="<?= e($label) ?>">
                    <input type="text" class="theme-hex" value="<?= e($val) ?>" maxlength="7" pattern="#[0-9a-fA-F]{6}" title="Код цвета, например #6f8f7f">
                    <span class="theme-color-label"><?= e($label) ?></span>
                </div>
                <?php endforeach; ?>
            </div>
        <?php endforeach; ?>
    </div>

    <div class="adm-card">
        <h2>Онлайн-касса (ЮKassa / Точка Банк)</h2>
        <p class="muted" style="margin-bottom:1rem">Для эквайринга Точка Банк подключите ЮKassa в личном кабинете банка и укажите shopId и секретный ключ ниже. URL для уведомлений: <code><?= e(url('pay/webhook')) ?></code></p>
        <label class="adm-check"><input type="checkbox" name="payments_enabled" <?= ($s['payments_enabled'] ?? '0') === '1' ? 'checked' : '' ?>> Принимать онлайн-оплату</label>
        <div class="adm-grid cols-2">
            <div class="adm-field"><label>shopId</label><input name="yookassa_shop_id" value="<?= $v('yookassa_shop_id') ?>"></div>
            <div class="adm-field"><label>Секретный ключ</label><input type="password" name="yookassa_secret_key" placeholder="<?= ($s['yookassa_secret_key'] ?? '') ? '•••••• (сохранён, оставьте пустым)' : 'test_... или live_...' ?>"></div>
        </div>
        <div style="background:rgba(243,237,227,.5);border-radius:12px;padding:14px;margin-top:.5rem">
            <label class="adm-check"><input type="checkbox" name="fiscal_enabled" <?= ($s['fiscal_enabled'] ?? '0') === '1' ? 'checked' : '' ?>> Формировать кассовые чеки (54-ФЗ)</label>
            <div class="adm-grid cols-2">
                <div class="adm-field"><label>Система налогообложения</label>
                    <select name="tax_system_code">
                        <?php $tsc = (int) ($s['tax_system_code'] ?? 2); foreach ([1=>'ОСН',2=>'УСН доход',3=>'УСН доход-расход',4=>'ЕНВД',5=>'ЕСХН',6=>'Патент'] as $k=>$l): ?>
                            <option value="<?= $k ?>" <?= $tsc===$k?'selected':'' ?>><?= e($l) ?></option>
                        <?php endforeach; ?>
                    </select>
                </div>
                <div class="adm-field"><label>Ставка НДС</label>
                    <select name="vat_code">
                        <?php $vc = (int) ($s['vat_code'] ?? 1); foreach ([1=>'Без НДС',2=>'0%',3=>'10%',4=>'20%',5=>'10/110',6=>'20/120'] as $k=>$l): ?>
                            <option value="<?= $k ?>" <?= $vc===$k?'selected':'' ?>><?= e($l) ?></option>
                        <?php endforeach; ?>
                    </select>
                </div>
            </div>
            <input type="hidden" name="payment_subject" value="<?= $v('payment_subject') ?: 'service' ?>">
            <input type="hidden" name="payment_mode" value="<?= $v('payment_mode') ?: 'full_payment' ?>">
        </div>
    </div>

    <button class="btn btn-primary">Сохранить настройки</button>
</form>
<script src="<?= e(asset('assets/js/admin-theme.js')) ?>"></script>
