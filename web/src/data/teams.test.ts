import { describe, expect, it } from "vitest";
import { canManage, canWrite, rolesInvitableBy } from "./teams";

describe("team role helpers mirror the database rules", () => {
  it("owners invite admins, members and viewers; admins only members and viewers", () => {
    expect(rolesInvitableBy("owner")).toEqual(["admin", "member", "viewer"]);
    expect(rolesInvitableBy("admin")).toEqual(["member", "viewer"]);
    expect(rolesInvitableBy("member")).toEqual([]);
    expect(rolesInvitableBy("viewer")).toEqual([]);
    expect(rolesInvitableBy(undefined)).toEqual([]);
  });

  it("only owners and admins manage; viewers never write", () => {
    expect(canManage("owner") && canManage("admin")).toBe(true);
    expect(canManage("member") || canManage("viewer")).toBe(false);
    expect(canWrite("member")).toBe(true);
    expect(canWrite("viewer")).toBe(false);
  });
});
