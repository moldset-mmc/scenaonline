import { z } from "zod";
export const specialties = ["Визажист", "Стилист", "Бьюти-мастер", "Салон / студия", "Другое"] as const;
export const features = ["Запись на услуги", "Портфолио", "Курсы", "Магазин", "Визитка и QR", "Нужна помощь с выбором"] as const;
export const styles = ["Светлый и воздушный", "Выразительный и яркий", "Сдержанный и элегантный", "Доверюсь вам"] as const;
export const readiness = ["Уже есть", "Создадим вместе", "Пока не знаю"] as const;
export const languages = ["Русский", "Română", "English"] as const;
export const blankAnswers = {
  name: "", brand: "", specialty: "", city: "", features: [] as string[], languages: ["Русский"],
  services: "", booking: "Обсудим вместе", style: "Доверюсь вам", inspiration: "", about: "",
  domainStatus: "Создадим вместе", domain: "", github: "Создадим вместе", vercel: "Создадим вместе",
  accountEmail: "", contact: "", timing: "Без спешки", notes: "", consent: false,
};
export type Answers = typeof blankAnswers;
const short = (max: number) => z.string().trim().max(max);
export const answerSchema = z.object({
  name: short(70).min(2, "Напишите, как к вам обращаться"), brand: short(80), specialty: z.enum(specialties, {errorMap:()=>({message:"Выберите вашу специализацию"})}), city: short(80),
  features: z.array(z.enum(features)).min(1, "Выберите хотя бы один вариант").max(6), languages: z.array(z.enum(languages)).min(1).max(3),
  services: short(450), booking: z.enum(["Заявка на сайте", "Через мессенджер", "Обсудим вместе"]), style: z.enum(styles), inspiration: short(200), about: short(220),
  domainStatus: z.enum(readiness), domain: short(120), github: z.enum(readiness), vercel: z.enum(readiness),
  accountEmail: short(160).refine(v => !v || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v), "Проверьте email"),
  contact: short(160).min(5, "Укажите Telegram, телефон или email").refine(v => /^@[a-zA-Z0-9_]{5,32}$/.test(v) || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || (/^[+\d ()-]{7,30}$/.test(v) && v.replace(/\D/g, "").length >= 7), "Введите @username, email или номер телефона"),
  timing: z.enum(["Как можно скорее", "В течение месяца", "Без спешки"]), notes: short(250),
  consent: z.literal(true, { errorMap: () => ({ message: "Нужно согласие на передачу анкеты" }) }),
}).strict();
export const payloadSchema = z.object({ id: z.string().uuid(), answers: answerSchema, website: z.string().max(0) }).strict();
export const MAX_PHOTOS = 6;
export const MAX_PHOTO_BYTES = 4 * 1024 * 1024;
export function telegramText(a: z.infer<typeof answerSchema>, id: string, galleryUrl?: string) {
  const value = (s: string) => s || "—";
  return ["НОВАЯ АНКЕТА · SCENA", `№ ${id}`, "", `${a.name} · ${a.specialty}`, `Бренд: ${value(a.brand)}`, `Город: ${value(a.city)}`, `Контакт: ${a.contact}`, "",
    `Нужно: ${a.features.join(", ")}`, `Языки: ${a.languages.join(", ")}`, `Запись: ${a.booking}`, `Услуги и цены:\n${value(a.services)}`, "", `Стиль: ${a.style}`, `Примеры: ${value(a.inspiration)}`,
    `О себе: ${value(a.about)}`, "", `Домен: ${a.domainStatus} · ${value(a.domain)}`, `GitHub: ${a.github}`, `Vercel: ${a.vercel}`, `Email для аккаунтов: ${value(a.accountEmail)}`,
    `Сроки: ${a.timing}`, `Комментарий: ${value(a.notes)}`, "", galleryUrl ? `Фотографии · закрытая ссылка на 30 дней:\n${galleryUrl}` : "Фотографии: не приложены",
    "Согласие на передачу анкеты и материалов: получено."].join("\n");
}
