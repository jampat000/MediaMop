using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Numerics;

namespace Weir.Core.Net;

/// <summary>An address as Python's <c>ipaddress</c> module parses and classifies it.</summary>
public sealed record PyIpAddress(bool IsV6, BigInteger Value)
{
    private static readonly PyIpNetwork[] V4Private =
    [
        PyIpNetwork.ParseV4("0.0.0.0", 8), PyIpNetwork.ParseV4("10.0.0.0", 8), PyIpNetwork.ParseV4("127.0.0.0", 8),
        PyIpNetwork.ParseV4("169.254.0.0", 16), PyIpNetwork.ParseV4("172.16.0.0", 12), PyIpNetwork.ParseV4("192.0.0.0", 29),
        PyIpNetwork.ParseV4("192.0.0.170", 31), PyIpNetwork.ParseV4("192.0.2.0", 24), PyIpNetwork.ParseV4("192.168.0.0", 16),
        PyIpNetwork.ParseV4("198.18.0.0", 15), PyIpNetwork.ParseV4("198.51.100.0", 24), PyIpNetwork.ParseV4("203.0.113.0", 24),
        PyIpNetwork.ParseV4("240.0.0.0", 4), PyIpNetwork.ParseV4("255.255.255.255", 32),
    ];

    private static readonly PyIpNetwork V4Shared = PyIpNetwork.ParseV4("100.64.0.0", 10);

    private static readonly PyIpNetwork[] V6Private =
    [
        PyIpNetwork.ParseV6("::1", 128), PyIpNetwork.ParseV6("::", 128), PyIpNetwork.ParseV6("::ffff:0:0", 96),
        PyIpNetwork.ParseV6("100::", 64), PyIpNetwork.ParseV6("2001::", 23), PyIpNetwork.ParseV6("2001:2::", 48),
        PyIpNetwork.ParseV6("2001:db8::", 32), PyIpNetwork.ParseV6("2001:10::", 28), PyIpNetwork.ParseV6("fc00::", 7),
        PyIpNetwork.ParseV6("fe80::", 10),
    ];

    private static readonly PyIpNetwork[] V6Reserved =
    [
        PyIpNetwork.ParseV6("::", 8), PyIpNetwork.ParseV6("100::", 8), PyIpNetwork.ParseV6("200::", 7), PyIpNetwork.ParseV6("400::", 6),
        PyIpNetwork.ParseV6("800::", 5), PyIpNetwork.ParseV6("1000::", 4), PyIpNetwork.ParseV6("4000::", 3), PyIpNetwork.ParseV6("6000::", 3),
        PyIpNetwork.ParseV6("8000::", 3), PyIpNetwork.ParseV6("a000::", 3), PyIpNetwork.ParseV6("c000::", 3), PyIpNetwork.ParseV6("e000::", 4),
        PyIpNetwork.ParseV6("f000::", 5), PyIpNetwork.ParseV6("f800::", 6), PyIpNetwork.ParseV6("fe00::", 9),
    ];

    public int Bits => IsV6 ? 128 : 32;

    /// <summary><c>ipaddress.ip_address(text)</c>: strict dotted-quad IPv4, or IPv6 (an optional <c>%scope</c> is kept out of the value).</summary>
    public static bool TryParse(string? text, out PyIpAddress address)
    {
        address = new PyIpAddress(false, BigInteger.Zero);
        if (string.IsNullOrEmpty(text))
        {
            return false;
        }

        if (TryParseV4(text, out var v4))
        {
            address = new PyIpAddress(false, v4);
            return true;
        }

        var hostPart = text;
        var percent = text.IndexOf('%', StringComparison.Ordinal);
        if (percent >= 0)
        {
            if (percent == text.Length - 1 || text[(percent + 1)..].Contains('/', StringComparison.Ordinal))
            {
                return false;
            }

            hostPart = text[..percent];
        }

        if (!hostPart.Contains(':', StringComparison.Ordinal) ||
            hostPart.Any(c => !(char.IsAsciiHexDigit(c) || c is ':' or '.')) ||
            !IPAddress.TryParse(hostPart, out var parsed) || parsed.AddressFamily != AddressFamily.InterNetworkV6)
        {
            return false;
        }

        address = new PyIpAddress(true, new BigInteger(parsed.GetAddressBytes(), isUnsigned: true, isBigEndian: true));
        return true;
    }

    internal static bool TryParseV4(string text, out BigInteger value)
    {
        value = BigInteger.Zero;
        var parts = text.Split('.');
        if (parts.Length != 4)
        {
            return false;
        }

        foreach (var part in parts)
        {
            if (part.Length is 0 or > 3 || part.Any(c => !char.IsAsciiDigit(c)) || (part.Length > 1 && part[0] == '0'))
            {
                return false;
            }

            var octet = int.Parse(part, NumberStyles.None, CultureInfo.InvariantCulture);
            if (octet > 255)
            {
                return false;
            }

            value = (value << 8) | octet;
        }

        return true;
    }

    public static PyIpAddress FromIpAddress(IPAddress address)
    {
        ArgumentNullException.ThrowIfNull(address);
        var bytes = address.GetAddressBytes();
        return new PyIpAddress(address.AddressFamily == AddressFamily.InterNetworkV6, new BigInteger(bytes, isUnsigned: true, isBigEndian: true));
    }

    /// <summary>The embedded IPv4 address of <c>::ffff:a.b.c.d</c>.</summary>
    public PyIpAddress? Ipv4Mapped => IsV6 && (Value >> 32) == 0xFFFF ? new PyIpAddress(false, Value & 0xFFFFFFFF) : null;

    public bool IsLoopback => IsV6 ? Value == 1 : In(PyIpNetwork.ParseV4("127.0.0.0", 8));

    public bool IsLinkLocal => IsV6 ? In(PyIpNetwork.ParseV6("fe80::", 10)) : In(PyIpNetwork.ParseV4("169.254.0.0", 16));

    public bool IsMulticast => IsV6 ? In(PyIpNetwork.ParseV6("ff00::", 8)) : In(PyIpNetwork.ParseV4("224.0.0.0", 4));

    public bool IsUnspecified => Value.IsZero;

    public bool IsReserved => IsV6 ? V6Reserved.Any(In) : In(PyIpNetwork.ParseV4("240.0.0.0", 4));

    public bool IsPrivate => IsV6
        ? Ipv4Mapped is { } mapped ? mapped.IsPrivate : V6Private.Any(In)
        : V4Private.Any(In);

    public bool IsGlobal => IsV6 ? !IsPrivate : !In(V4Shared) && !IsPrivate;

    public bool In(PyIpNetwork network)
    {
        ArgumentNullException.ThrowIfNull(network);
        return network.Contains(this);
    }
}

/// <summary><c>ipaddress.ip_network(text, strict=...)</c>.</summary>
public sealed record PyIpNetwork(bool IsV6, BigInteger NetworkAddress, int PrefixLength)
{
    public static PyIpNetwork ParseV4(string address, int prefix) =>
        PyIpAddress.TryParse(address, out var parsed) && !parsed.IsV6
            ? new PyIpNetwork(false, parsed.Value, prefix)
            : throw new ArgumentException("Invalid IPv4 network.", nameof(address));

    public static PyIpNetwork ParseV6(string address, int prefix) =>
        PyIpAddress.TryParse(address, out var parsed) && parsed.IsV6
            ? new PyIpNetwork(true, parsed.Value, prefix)
            : throw new ArgumentException("Invalid IPv6 network.", nameof(address));

    /// <summary>
    /// <paramref name="strict"/> = <see langword="false"/> masks host bits (<c>10.0.0.5/24</c> is <c>10.0.0.0/24</c>);
    /// <see langword="true"/> refuses them. A bare address is a single-host network.
    /// </summary>
    public static bool TryParse(string? text, bool strict, out PyIpNetwork network)
    {
        network = new PyIpNetwork(false, BigInteger.Zero, 32);
        if (string.IsNullOrEmpty(text))
        {
            return false;
        }

        var slash = text.IndexOf('/', StringComparison.Ordinal);
        var addressText = slash < 0 ? text : text[..slash];
        if (!PyIpAddress.TryParse(addressText, out var address) || (address.IsV6 && addressText.Contains('%', StringComparison.Ordinal)))
        {
            return false;
        }

        var bits = address.Bits;
        var prefix = bits;
        if (slash >= 0)
        {
            var prefixText = text[(slash + 1)..];
            if (prefixText.Length > 0 && prefixText.All(char.IsAsciiDigit) && (prefixText.Length == 1 || prefixText[0] != '0'))
            {
                if (!int.TryParse(prefixText, NumberStyles.None, CultureInfo.InvariantCulture, out prefix) || prefix > bits)
                {
                    return false;
                }
            }
            else if (!address.IsV6 && PyIpAddress.TryParseV4(prefixText, out var mask) && TryMaskToPrefix(mask, out var fromMask))
            {
                prefix = fromMask;
            }
            else
            {
                return false;
            }
        }

        var hostMask = (BigInteger.One << (bits - prefix)) - 1;
        if (strict && (address.Value & hostMask) != 0)
        {
            return false;
        }

        network = new PyIpNetwork(address.IsV6, address.Value & ~hostMask & ((BigInteger.One << bits) - 1), prefix);
        return true;
    }

    /// <summary>The network address in network byte order (4 or 16 bytes).</summary>
    public byte[] AddressBytes()
    {
        var length = IsV6 ? 16 : 4;
        var raw = NetworkAddress.ToByteArray(isUnsigned: true, isBigEndian: true);
        var bytes = new byte[length];
        raw.AsSpan(Math.Max(0, raw.Length - length)).CopyTo(bytes.AsSpan(Math.Max(0, length - raw.Length)));
        return bytes;
    }

    public bool Contains(PyIpAddress address)
    {
        ArgumentNullException.ThrowIfNull(address);
        if (address.IsV6 != IsV6)
        {
            return false;
        }

        var bits = IsV6 ? 128 : 32;
        return (address.Value >> (bits - PrefixLength)) == (NetworkAddress >> (bits - PrefixLength));
    }

    private static bool TryMaskToPrefix(BigInteger mask, out int prefix)
    {
        prefix = 0;
        var seenZero = false;
        for (var bit = 31; bit >= 0; bit--)
        {
            var set = ((mask >> bit) & 1) == 1;
            if (set && seenZero)
            {
                return false;
            }

            if (set)
            {
                prefix++;
            }
            else
            {
                seenZero = true;
            }
        }

        return true;
    }
}
