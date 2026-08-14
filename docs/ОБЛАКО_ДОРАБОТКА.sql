-- Разделение визитов по менеджерам в общей облачной панели.
-- Выполнить один раз в Supabase → SQL Editor, проект bhs-analytics.
--
-- Зачем: ноутбуков и приборов много, облако одно. Сейчас менеджер виден
-- только по приставке в session_id (например anna-260814-143015), и панель
-- не умеет по нему фильтровать. Эти две колонки делают его полем.

alter table neuro_cards add column if not exists operator text;
alter table neuro_cards add column if not exists operator_name text;

create index if not exists neuro_cards_operator_idx on neuro_cards(operator);

-- Проставить менеджера уже загруженным визитам по приставке в имени:
update neuro_cards
   set operator = split_part(session_id, '-', 1)
 where operator is null
   and session_id like '%-%-%';
