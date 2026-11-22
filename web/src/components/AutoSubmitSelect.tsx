"use client";

import type { ReactNode } from "react";

/** <select> qui envoie son formulaire (GET) dès qu'on change de valeur —
 *  pas besoin d'appuyer sur « Voir » sur mobile. Le bouton reste là si le
 *  JavaScript n'est pas chargé. */
export default function AutoSubmitSelect({
  name,
  defaultValue,
  className,
  children,
}: {
  name: string;
  defaultValue: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <select
      name={name}
      defaultValue={defaultValue}
      className={className}
      onChange={(e) => e.currentTarget.form?.requestSubmit()}
    >
      {children}
    </select>
  );
}
