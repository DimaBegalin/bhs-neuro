-- Хранилище визитов нейропрофориентации.
-- Выполнить один раз в Supabase, раздел SQL Editor.
--
-- База общая на всех менеджеров, но каждый видит только свои визиты.
-- Держится это не на странице, а на правилах доступа самой базы: даже зная
-- адрес и ключ, чужие записи прочитать нельзя.

create table if not exists neuro_visits (
  session_id    text primary key,
  manager_id    uuid not null references auth.users(id) on delete cascade,
  student_name  text not null default '',
  grade         text not null default '',
  track         text not null default 'ru',
  started_at    text not null default '',
  has_eeg       boolean not null default false,
  iaf           numeric,
  pulse_bpm     integer,
  quality       jsonb,
  domains       jsonb,
  -- готовая страница разбора: панель открывает её как есть, поэтому
  -- отчёт доступен с любого устройства, а не только с ноутбука замера
  report_html   text,
  created_at    timestamptz not null default now()
);

create index if not exists neuro_visits_manager_idx
  on neuro_visits(manager_id, created_at desc);

alter table neuro_visits enable row level security;

-- Менеджер работает только со своими визитами. Три правила вместо одного
-- потому, что postgres проверяет чтение, вставку и правку раздельно.
drop policy if exists "свои визиты видны" on neuro_visits;
create policy "свои визиты видны" on neuro_visits
  for select to authenticated using (auth.uid() = manager_id);

drop policy if exists "свои визиты добавляются" on neuro_visits;
create policy "свои визиты добавляются" on neuro_visits
  for insert to authenticated with check (auth.uid() = manager_id);

drop policy if exists "свои визиты правятся" on neuro_visits;
create policy "свои визиты правятся" on neuro_visits
  for update to authenticated
  using (auth.uid() = manager_id) with check (auth.uid() = manager_id);

-- Удаление намеренно не разрешено никому: визит это результат замера
-- ребёнка, и стирать его случайным нажатием нельзя. Чистка только руками
-- через дашборд.
