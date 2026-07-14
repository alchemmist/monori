import { accountIcon, DEFAULT_ACCOUNT_COLOR } from "./accountIcons.js";

/** The account's visual token: either a custom uploaded image, or a glyph tinted
 * with the account color — solid glyph + border over a translucent tile. */
export default function AccountBadge({ account, size = 30 }) {
  const style = { width: size, height: size };
  if (account.iconImage) {
    return (
      <span className="acct-badge acct-badge_image" style={style}>
        <img src={account.iconImage} alt="" />
      </span>
    );
  }
  const Icon = accountIcon(account.icon);
  const color = account.color || DEFAULT_ACCOUNT_COLOR;
  return (
    <span
      className="acct-badge"
      style={{
        ...style,
        color,
        background: `color-mix(in srgb, ${color} 14%, transparent)`,
        borderColor: `color-mix(in srgb, ${color} 42%, transparent)`,
      }}
    >
      <Icon width={Math.round(size * 0.56)} height={Math.round(size * 0.56)} />
    </span>
  );
}
