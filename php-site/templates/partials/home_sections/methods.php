<?php /** @var array $blocks $section */ ?>
<section class="section">
    <div class="container">
        <h2 class="section-center"><?= e($section['title'] ?: $blocks['methods_title']) ?></h2>
        <div class="methods-grid">
            <?php
            $methods = [
                ['Клиническая психология', 'Профессиональная диагностика и работа с тревожными, депрессивными и невротическими состояниями.'],
                ['Системная семейная терапия', 'Помощь парам и семьям: восстановление контакта, доверия и тепла в отношениях.'],
                ['ACT — терапия принятия', 'Развитие психологической гибкости и умения жить в согласии со своими ценностями.'],
                ['Эмоционально-фокусированный подход', 'Бережная работа с эмоциями и привязанностью в паре и индивидуально.'],
            ];
            foreach ($methods as $m): ?>
                <div class="method">
                    <div class="method-ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 12.5l5 5 11-11" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
                    <h3><?= e($m[0]) ?></h3>
                    <p><?= e($m[1]) ?></p>
                </div>
            <?php endforeach; ?>
        </div>
    </div>
</section>
