"use client";

import { getCountries, getCountryCallingCode, parsePhoneNumberFromString, type CountryCode } from "libphonenumber-js";
import { useState } from "react";

type Props = {
  value: string | null;
  onChange: (value: string | null) => void;
};

const displayNames = new Intl.DisplayNames(["en"], { type: "region" });
const countries = getCountries()
  .map((code) => ({
    code,
    name: displayNames.of(code) ?? code,
    callingCode: getCountryCallingCode(code),
  }))
  .sort((a, b) => a.name.localeCompare(b.name));

function splitNumber(value: string | null): { country: CountryCode | ""; national: string } {
  if (!value) return { country: "", national: "" };
  const parsed = parsePhoneNumberFromString(value);
  if (parsed?.country) return { country: parsed.country, national: parsed.formatNational() };
  return { country: "", national: value };
}

export function PhoneNumberField({ value, onChange }: Props) {
  const initial = splitNumber(value);
  const [country, setCountry] = useState<CountryCode | "">(initial.country);
  const [national, setNational] = useState(initial.national);

  const reportNumber = (nextCountry: CountryCode | "", nextNational: string) => {
    const digits = nextNational.replace(/\D/g, "");
    if (!nextCountry || !digits) {
      onChange(null);
      return;
    }
    const parsed = parsePhoneNumberFromString(nextNational, nextCountry);
    const localDigits = parsed?.nationalNumber ?? digits.replace(/^0+/, "");
    onChange(`+${getCountryCallingCode(nextCountry)}${localDigits}`);
  };

  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(12rem,1fr)_2fr]">
      <label className="text-sm">Country code
        <select className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm" value={country} onChange={(e) => {
          const next = e.target.value as CountryCode | "";
          setCountry(next);
          reportNumber(next, national);
        }}>
          <option value="">Choose a country</option>
          {countries.map((item) => <option key={item.code} value={item.code}>{item.name} (+{item.callingCode})</option>)}
        </select>
      </label>
      <label className="text-sm">Mobile
        <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm" type="tel" inputMode="tel" autoComplete="tel-national" placeholder="e.g. 7700 900123" value={national} onChange={(e) => {
          setNational(e.target.value);
          reportNumber(country, e.target.value);
        }} />
      </label>
    </div>
  );
}
