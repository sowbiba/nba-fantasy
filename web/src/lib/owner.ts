export function isOwnerEmail(email: string | null | undefined, owner: string | undefined): boolean {
  if (!email || !owner) return false;
  return email.trim().toLowerCase() === owner.trim().toLowerCase();
}
