"""Один учебник: Markdown в Git и HTML на сайте."""
import markdown
from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET
from .lessons import LESSONS

@require_GET
def index(request):
    return render(request, "academy/index.html", {"lessons": LESSONS})

@require_GET
def lesson(request, slug):
    selected = next((item for item in LESSONS if item["slug"] == slug), None)
    if selected is None:
        raise Http404("Урок не найден")
    source = (settings.BASE_DIR / "docs" / selected["filename"]).read_text(encoding="utf-8")
    # Название уже выводится заголовком страницы; не дублируем первый Markdown H1.
    body = source.split("\n", 1)[1] if source.startswith("# ") else source
    html = markdown.markdown(body, extensions=["fenced_code", "tables", "toc"])
    for item in LESSONS:
        html = html.replace('href="' + item["filename"],
                            'href="' + reverse("academy:lesson", args=[item["slug"]]))
    html = html.replace('href="README.md"', 'href="' + reverse("academy:index") + '"')
    position = selected["number"] - 1
    return render(request, "academy/lesson.html", {
        "lesson": selected, "lessons": LESSONS,
        # Только доверенные файлы репозитория! Для пользовательского Markdown
        # нужен HTML-санитайзер: mark_safe сам ничего не очищает.
        "content_html": mark_safe(html),
        "previous_lesson": LESSONS[position - 1] if position else None,
        "next_lesson": LESSONS[position + 1] if position + 1 < len(LESSONS) else None,
    })
