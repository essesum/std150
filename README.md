# СТД 150 · Режиссёрская партитура

Закрытый рабочий сайт видеосценографии гала-концерта к 150-летию Союза театральных деятелей.
Сайт: https://essesum.github.io/std150/ (пароль — у Кати, передаётся отдельным сообщением).

Всё содержимое зашифровано (AES-256-GCM, ключ из пароля через PBKDF2-SHA256, 600 000 итераций):
`index.html` — шифротекст страницы с данными, `a/` — шифротекст каждой картинки и видео, `site.json` — соль.
Расшифровка происходит в браузере после ввода пароля. Открытых файлов в репозитории нет.

## Как устроено

```
index.html               зашифрованная страница (собирается, руками не править)
a/<id>                   зашифрованные картинки и превью видео
site.json                соль ключа (публичная, не секрет)
std150-source.zip.enc    зашифрованный архив исходников (папка private/) для передачи проекта
tools/std150.py          CLI: правки сцен, версии, сборка, публикация
tools/gate.html          экран ввода пароля
tools/crypt.py           шифрование/расшифровка архива
private/                 открытые исходники — только локально, в git не попадает
```

## Первый запуск на новой машине

```bash
git clone https://github.com/essesum/std150.git && cd std150
pip install cryptography            # и ffmpeg для превью видео: brew install ffmpeg
python3 tools/crypt.py decrypt std150-source.zip.enc std150-source.zip   # спросит пароль
mkdir private && unzip std150-source.zip -d private
```

Первым открыть `private/docs/HANDOFF.md` — где проект сейчас и что дальше.

## Ежедневная работа

Пароль берётся из `STD150_PASSWORD` или файла `~/.std150_pass`.

```bash
python3 tools/std150.py summary                         # статусы, дни до сдачи, открытые вопросы
python3 tools/std150.py show 7а                         # всё по сцене
python3 tools/std150.py set 7а status=anim              # статусы: scen setup anim master done
python3 tools/std150.py add-version 4 render.mp4 --surface rear --by "Имя" --note "что изменилось"
python3 tools/std150.py add-version 13 https://disk.yandex.ru/i/… --surface net
python3 tools/std150.py comment 8 "текст" --by "Имя"
python3 tools/std150.py ask 20а "вопрос режиссёру"
python3 tools/std150.py answer q21 "ответ" --by "Стародубцев"
python3 tools/std150.py publish -m "что поменялось"     # сборка + проверка + commit + push
python3 tools/std150.py publish --archive               # то же + обновить архив исходников
```

`add-version` делает лёгкое превью (видео — mp4 960 px до 60 с без звука, картинка — jpg 1600 px).
Оригиналы в DXV3 на сайт не кладутся: они идут на USB по ТЗ площадки.

Смена пароля: удалить `site.json`, задать новый пароль, `publish --archive`. Старые сохранённые на устройствах ключи перестанут подходить.
