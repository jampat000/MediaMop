using System.Buffers.Binary;
using System.Numerics;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace Weir.Core.Security;

/// <summary>The three Argon2 variants, numbered as in RFC 9106.</summary>
public enum Argon2Type
{
    Argon2d = 0,
    Argon2i = 1,
    Argon2id = 2,
}

/// <summary>
/// Argon2 (RFC 9106), a straight port of the reference implementation that argon2-cffi wraps.
/// Versions 0x10 and 0x13 are supported so any hash argon2-cffi produced verifies.
/// </summary>
public static class Argon2
{
    public const int Version13 = 0x13;
    public const int Version10 = 0x10;

    private const int BlockSize = 1024;
    private const int WordsInBlock = 128;
    private const int SyncPoints = 4;

    public static byte[] Hash(
        Argon2Type type,
        int version,
        ReadOnlySpan<byte> password,
        ReadOnlySpan<byte> salt,
        ReadOnlySpan<byte> secret,
        ReadOnlySpan<byte> associatedData,
        int iterations,
        int memoryKib,
        int parallelism,
        int hashLength)
    {
        if (iterations < 1 || parallelism < 1 || hashLength < 4 || memoryKib < 8 * parallelism)
        {
            throw new ArgumentOutOfRangeException(nameof(iterations), "Argon2 parameters are out of range.");
        }

        if (version is not (Version10 or Version13))
        {
            throw new ArgumentOutOfRangeException(nameof(version), "Unsupported Argon2 version.");
        }

        var lanes = parallelism;
        var memoryBlocks = SyncPoints * lanes * (memoryKib / (SyncPoints * lanes));
        var segmentLength = memoryBlocks / (lanes * SyncPoints);
        var laneLength = segmentLength * SyncPoints;

        Span<byte> h0 = stackalloc byte[72];
        InitialHash(type, version, password, salt, secret, associatedData, iterations, memoryKib, lanes, hashLength, h0[..64]);

        var memory = new ulong[memoryBlocks * WordsInBlock];
        Span<byte> blockBytes = stackalloc byte[BlockSize];
        for (var lane = 0; lane < lanes; lane++)
        {
            BinaryPrimitives.WriteUInt32LittleEndian(h0[64..], 0);
            BinaryPrimitives.WriteUInt32LittleEndian(h0[68..], (uint)lane);
            Blake2b.VariableLengthHash(h0, blockBytes);
            LoadBlock(blockBytes, memory.AsSpan(lane * laneLength * WordsInBlock, WordsInBlock));
            BinaryPrimitives.WriteUInt32LittleEndian(h0[64..], 1);
            Blake2b.VariableLengthHash(h0, blockBytes);
            LoadBlock(blockBytes, memory.AsSpan(((lane * laneLength) + 1) * WordsInBlock, WordsInBlock));
        }

        var addressBlock = new ulong[WordsInBlock];
        var inputBlock = new ulong[WordsInBlock];
        var zeroBlock = new ulong[WordsInBlock];
        var scratch = new ulong[WordsInBlock * 2];
        for (var pass = 0; pass < iterations; pass++)
        {
            for (var slice = 0; slice < SyncPoints; slice++)
            {
                for (var lane = 0; lane < lanes; lane++)
                {
                    FillSegment(
                        memory, type, version, pass, lane, slice, lanes, laneLength, segmentLength, memoryBlocks, iterations,
                        addressBlock, inputBlock, zeroBlock, scratch);
                }
            }
        }

        var final = new ulong[WordsInBlock];
        for (var lane = 0; lane < lanes; lane++)
        {
            var last = memory.AsSpan((((lane * laneLength) + laneLength) - 1) * WordsInBlock, WordsInBlock);
            for (var i = 0; i < WordsInBlock; i++)
            {
                final[i] ^= last[i];
            }
        }

        for (var i = 0; i < WordsInBlock; i++)
        {
            BinaryPrimitives.WriteUInt64LittleEndian(blockBytes[(i * 8)..], final[i]);
        }

        var tag = new byte[hashLength];
        Blake2b.VariableLengthHash(blockBytes, tag);
        Array.Clear(memory);
        return tag;
    }

    private static void InitialHash(
        Argon2Type type,
        int version,
        ReadOnlySpan<byte> password,
        ReadOnlySpan<byte> salt,
        ReadOnlySpan<byte> secret,
        ReadOnlySpan<byte> associatedData,
        int iterations,
        int memoryKib,
        int lanes,
        int hashLength,
        Span<byte> output)
    {
        var buffer = new byte[(4 * 10) + password.Length + salt.Length + secret.Length + associatedData.Length];
        var span = buffer.AsSpan();
        var pos = 0;
        void Put(uint value)
        {
            BinaryPrimitives.WriteUInt32LittleEndian(buffer.AsSpan(pos), value);
            pos += 4;
        }

        Put((uint)lanes);
        Put((uint)hashLength);
        Put((uint)memoryKib);
        Put((uint)iterations);
        Put((uint)version);
        Put((uint)type);
        Put((uint)password.Length);
        password.CopyTo(span[pos..]);
        pos += password.Length;
        Put((uint)salt.Length);
        salt.CopyTo(span[pos..]);
        pos += salt.Length;
        Put((uint)secret.Length);
        secret.CopyTo(span[pos..]);
        pos += secret.Length;
        Put((uint)associatedData.Length);
        associatedData.CopyTo(span[pos..]);
        Blake2b.Hash(buffer, output[..64]);
        CryptographicZero(buffer);
    }

    private static void CryptographicZero(byte[] buffer) => System.Security.Cryptography.CryptographicOperations.ZeroMemory(buffer);

    private static void LoadBlock(ReadOnlySpan<byte> bytes, Span<ulong> block)
    {
        for (var i = 0; i < WordsInBlock; i++)
        {
            block[i] = BinaryPrimitives.ReadUInt64LittleEndian(bytes[(i * 8)..]);
        }
    }

    private static void FillSegment(
        ulong[] memory,
        Argon2Type type,
        int version,
        int pass,
        int lane,
        int slice,
        int lanes,
        int laneLength,
        int segmentLength,
        int memoryBlocks,
        int iterations,
        ulong[] addressBlock,
        ulong[] inputBlock,
        ulong[] zeroBlock,
        ulong[] scratch)
    {
        var dataIndependent = type == Argon2Type.Argon2i || (type == Argon2Type.Argon2id && pass == 0 && slice < SyncPoints / 2);
        if (dataIndependent)
        {
            Array.Clear(inputBlock);
            inputBlock[0] = (ulong)pass;
            inputBlock[1] = (ulong)lane;
            inputBlock[2] = (ulong)slice;
            inputBlock[3] = (ulong)memoryBlocks;
            inputBlock[4] = (ulong)iterations;
            inputBlock[5] = (ulong)type;
        }

        var startingIndex = 0;
        if (pass == 0 && slice == 0)
        {
            startingIndex = 2;
            if (dataIndependent)
            {
                NextAddresses(addressBlock, inputBlock, zeroBlock, scratch);
            }
        }

        var currentOffset = (lane * laneLength) + (slice * segmentLength) + startingIndex;
        var previousOffset = currentOffset % laneLength == 0 ? currentOffset + laneLength - 1 : currentOffset - 1;
        for (var i = startingIndex; i < segmentLength; i++, currentOffset++, previousOffset++)
        {
            if (currentOffset % laneLength == 1)
            {
                previousOffset = currentOffset - 1;
            }

            ulong pseudoRandom;
            if (dataIndependent)
            {
                if (i % WordsInBlock == 0)
                {
                    NextAddresses(addressBlock, inputBlock, zeroBlock, scratch);
                }

                pseudoRandom = addressBlock[i % WordsInBlock];
            }
            else
            {
                pseudoRandom = memory[previousOffset * WordsInBlock];
            }

            var referenceLane = (int)((pseudoRandom >> 32) % (ulong)lanes);
            if (pass == 0 && slice == 0)
            {
                referenceLane = lane;
            }

            var referenceIndex = IndexAlpha(pass, slice, i, laneLength, segmentLength, (uint)pseudoRandom, referenceLane == lane);
            var withXor = version != Version10 && pass != 0;
            FillBlock(
                memory.AsSpan(previousOffset * WordsInBlock, WordsInBlock),
                memory.AsSpan(((laneLength * referenceLane) + (int)referenceIndex) * WordsInBlock, WordsInBlock),
                memory.AsSpan(currentOffset * WordsInBlock, WordsInBlock),
                withXor,
                scratch);
        }
    }

    private static void NextAddresses(ulong[] addressBlock, ulong[] inputBlock, ulong[] zeroBlock, ulong[] scratch)
    {
        inputBlock[6]++;
        FillBlock(zeroBlock, inputBlock, addressBlock, withXor: false, scratch);
        var copy = addressBlock.AsSpan().ToArray();
        FillBlock(zeroBlock, copy, addressBlock, withXor: false, scratch);
    }

    private static uint IndexAlpha(int pass, int slice, int index, int laneLength, int segmentLength, uint pseudoRandom, bool sameLane)
    {
        uint referenceAreaSize;
        unchecked
        {
            if (pass == 0)
            {
                if (slice == 0)
                {
                    referenceAreaSize = (uint)(index - 1);
                }
                else if (sameLane)
                {
                    referenceAreaSize = (uint)((slice * segmentLength) + index - 1);
                }
                else
                {
                    referenceAreaSize = (uint)((slice * segmentLength) + (index == 0 ? -1 : 0));
                }
            }
            else if (sameLane)
            {
                referenceAreaSize = (uint)(laneLength - segmentLength + index - 1);
            }
            else
            {
                referenceAreaSize = (uint)(laneLength - segmentLength + (index == 0 ? -1 : 0));
            }

            ulong relativePosition = pseudoRandom;
            relativePosition = (relativePosition * relativePosition) >> 32;
            relativePosition = referenceAreaSize - 1 - ((referenceAreaSize * relativePosition) >> 32);
            ulong startPosition = 0;
            if (pass != 0)
            {
                startPosition = slice == SyncPoints - 1 ? 0UL : (ulong)((slice + 1) * segmentLength);
            }

            return (uint)((startPosition + relativePosition) % (ulong)laneLength);
        }
    }

    private static void FillBlock(ReadOnlySpan<ulong> previous, ReadOnlySpan<ulong> reference, Span<ulong> next, bool withXor, ulong[] scratch)
    {
        var r = scratch.AsSpan(0, WordsInBlock);
        var tmp = scratch.AsSpan(WordsInBlock, WordsInBlock);
        for (var i = 0; i < WordsInBlock; i++)
        {
            r[i] = reference[i] ^ previous[i];
        }

        r.CopyTo(tmp);
        if (withXor)
        {
            for (var i = 0; i < WordsInBlock; i++)
            {
                tmp[i] ^= next[i];
            }
        }

        ref var v = ref MemoryMarshal.GetReference(r);
        for (var i = 0; i < 8; i++)
        {
            var o = 16 * i;
            Round(
                ref Unsafe.Add(ref v, o), ref Unsafe.Add(ref v, o + 1), ref Unsafe.Add(ref v, o + 2), ref Unsafe.Add(ref v, o + 3),
                ref Unsafe.Add(ref v, o + 4), ref Unsafe.Add(ref v, o + 5), ref Unsafe.Add(ref v, o + 6), ref Unsafe.Add(ref v, o + 7),
                ref Unsafe.Add(ref v, o + 8), ref Unsafe.Add(ref v, o + 9), ref Unsafe.Add(ref v, o + 10), ref Unsafe.Add(ref v, o + 11),
                ref Unsafe.Add(ref v, o + 12), ref Unsafe.Add(ref v, o + 13), ref Unsafe.Add(ref v, o + 14), ref Unsafe.Add(ref v, o + 15));
        }

        for (var i = 0; i < 8; i++)
        {
            var o = 2 * i;
            Round(
                ref Unsafe.Add(ref v, o), ref Unsafe.Add(ref v, o + 1), ref Unsafe.Add(ref v, o + 16), ref Unsafe.Add(ref v, o + 17),
                ref Unsafe.Add(ref v, o + 32), ref Unsafe.Add(ref v, o + 33), ref Unsafe.Add(ref v, o + 48), ref Unsafe.Add(ref v, o + 49),
                ref Unsafe.Add(ref v, o + 64), ref Unsafe.Add(ref v, o + 65), ref Unsafe.Add(ref v, o + 80), ref Unsafe.Add(ref v, o + 81),
                ref Unsafe.Add(ref v, o + 96), ref Unsafe.Add(ref v, o + 97), ref Unsafe.Add(ref v, o + 112), ref Unsafe.Add(ref v, o + 113));
        }

        for (var i = 0; i < WordsInBlock; i++)
        {
            next[i] = tmp[i] ^ r[i];
        }
    }

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    private static void Round(
        ref ulong v0, ref ulong v1, ref ulong v2, ref ulong v3, ref ulong v4, ref ulong v5, ref ulong v6, ref ulong v7,
        ref ulong v8, ref ulong v9, ref ulong v10, ref ulong v11, ref ulong v12, ref ulong v13, ref ulong v14, ref ulong v15)
    {
        G(ref v0, ref v4, ref v8, ref v12);
        G(ref v1, ref v5, ref v9, ref v13);
        G(ref v2, ref v6, ref v10, ref v14);
        G(ref v3, ref v7, ref v11, ref v15);
        G(ref v0, ref v5, ref v10, ref v15);
        G(ref v1, ref v6, ref v11, ref v12);
        G(ref v2, ref v7, ref v8, ref v13);
        G(ref v3, ref v4, ref v9, ref v14);
    }

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    private static void G(ref ulong a, ref ulong b, ref ulong c, ref ulong d)
    {
        unchecked
        {
            a = a + b + (2 * (a & 0xFFFFFFFF) * (b & 0xFFFFFFFF));
            d = BitOperations.RotateRight(d ^ a, 32);
            c = c + d + (2 * (c & 0xFFFFFFFF) * (d & 0xFFFFFFFF));
            b = BitOperations.RotateRight(b ^ c, 24);
            a = a + b + (2 * (a & 0xFFFFFFFF) * (b & 0xFFFFFFFF));
            d = BitOperations.RotateRight(d ^ a, 16);
            c = c + d + (2 * (c & 0xFFFFFFFF) * (d & 0xFFFFFFFF));
            b = BitOperations.RotateRight(b ^ c, 63);
        }
    }
}

/// <summary>BLAKE2b (RFC 7693), unkeyed, and Argon2's variable-length <c>H'</c>.</summary>
public static class Blake2b
{
    private static readonly ulong[] IV =
    [
        0x6A09E667F3BCC908UL, 0xBB67AE8584CAA73BUL, 0x3C6EF372FE94F82BUL, 0xA54FF53A5F1D36F1UL,
        0x510E527FADE682D1UL, 0x9B05688C2B3E6C1FUL, 0x1F83D9ABFB41BD6BUL, 0x5BE0CD19137E2179UL,
    ];

    private static readonly byte[][] Sigma =
    [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        [14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3],
        [11, 8, 12, 0, 5, 2, 15, 13, 10, 14, 3, 6, 7, 1, 9, 4],
        [7, 9, 3, 1, 13, 12, 11, 14, 2, 6, 5, 10, 4, 0, 15, 8],
        [9, 0, 5, 7, 2, 4, 10, 15, 14, 1, 11, 12, 6, 8, 3, 13],
        [2, 12, 6, 10, 0, 11, 8, 3, 4, 13, 7, 5, 15, 14, 1, 9],
        [12, 5, 1, 15, 14, 13, 4, 10, 0, 7, 6, 3, 9, 2, 8, 11],
        [13, 11, 7, 14, 12, 1, 3, 9, 5, 0, 15, 4, 8, 6, 2, 10],
        [6, 15, 14, 9, 11, 3, 0, 8, 12, 2, 13, 7, 1, 4, 10, 5],
        [10, 2, 8, 4, 7, 6, 1, 5, 15, 11, 9, 14, 3, 12, 13, 0],
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        [14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3],
    ];

    /// <summary>BLAKE2b with an output of <paramref name="output"/>.Length bytes (1..64).</summary>
    public static void Hash(ReadOnlySpan<byte> input, Span<byte> output)
    {
        var outLength = output.Length;
        if (outLength is < 1 or > 64)
        {
            throw new ArgumentOutOfRangeException(nameof(output));
        }

        Span<ulong> h = stackalloc ulong[8];
        IV.CopyTo(h);
        h[0] ^= 0x01010000UL ^ (ulong)outLength;
        Span<ulong> m = stackalloc ulong[16];
        Span<byte> block = stackalloc byte[128];
        ulong counter = 0;
        var offset = 0;
        while (input.Length - offset > 128)
        {
            counter += 128;
            for (var i = 0; i < 16; i++)
            {
                m[i] = BinaryPrimitives.ReadUInt64LittleEndian(input[(offset + (i * 8))..]);
            }

            Compress(h, m, counter, last: false);
            offset += 128;
        }

        block.Clear();
        var remaining = input.Length - offset;
        input[offset..].CopyTo(block);
        counter += (ulong)remaining;
        for (var i = 0; i < 16; i++)
        {
            m[i] = BinaryPrimitives.ReadUInt64LittleEndian(block[(i * 8)..]);
        }

        Compress(h, m, counter, last: true);
        Span<byte> full = stackalloc byte[64];
        for (var i = 0; i < 8; i++)
        {
            BinaryPrimitives.WriteUInt64LittleEndian(full[(i * 8)..], h[i]);
        }

        full[..outLength].CopyTo(output);
    }

    /// <summary>Argon2's <c>H'</c>: BLAKE2b extended to any output length.</summary>
    public static void VariableLengthHash(ReadOnlySpan<byte> input, Span<byte> output)
    {
        var outLength = output.Length;
        var prefixed = new byte[4 + input.Length];
        BinaryPrimitives.WriteUInt32LittleEndian(prefixed, (uint)outLength);
        input.CopyTo(prefixed.AsSpan(4));
        if (outLength <= 64)
        {
            Hash(prefixed, output);
            return;
        }

        Span<byte> v = stackalloc byte[64];
        Hash(prefixed, v);
        v[..32].CopyTo(output);
        var written = 32;
        Span<byte> next = stackalloc byte[64];
        while (outLength - written > 64)
        {
            Hash(v, next);
            next.CopyTo(v);
            v[..32].CopyTo(output[written..]);
            written += 32;
        }

        Hash(v, output[written..]);
    }

    private static void Compress(Span<ulong> h, ReadOnlySpan<ulong> m, ulong counter, bool last)
    {
        Span<ulong> v = stackalloc ulong[16];
        h.CopyTo(v);
        IV.CopyTo(v[8..]);
        v[12] ^= counter;
        if (last)
        {
            v[14] = ~v[14];
        }

        for (var round = 0; round < 12; round++)
        {
            var s = Sigma[round];
            Mix(v, 0, 4, 8, 12, m[s[0]], m[s[1]]);
            Mix(v, 1, 5, 9, 13, m[s[2]], m[s[3]]);
            Mix(v, 2, 6, 10, 14, m[s[4]], m[s[5]]);
            Mix(v, 3, 7, 11, 15, m[s[6]], m[s[7]]);
            Mix(v, 0, 5, 10, 15, m[s[8]], m[s[9]]);
            Mix(v, 1, 6, 11, 12, m[s[10]], m[s[11]]);
            Mix(v, 2, 7, 8, 13, m[s[12]], m[s[13]]);
            Mix(v, 3, 4, 9, 14, m[s[14]], m[s[15]]);
        }

        for (var i = 0; i < 8; i++)
        {
            h[i] ^= v[i] ^ v[i + 8];
        }
    }

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    private static void Mix(Span<ulong> v, int a, int b, int c, int d, ulong x, ulong y)
    {
        unchecked
        {
            v[a] = v[a] + v[b] + x;
            v[d] = BitOperations.RotateRight(v[d] ^ v[a], 32);
            v[c] = v[c] + v[d];
            v[b] = BitOperations.RotateRight(v[b] ^ v[c], 24);
            v[a] = v[a] + v[b] + y;
            v[d] = BitOperations.RotateRight(v[d] ^ v[a], 16);
            v[c] = v[c] + v[d];
            v[b] = BitOperations.RotateRight(v[b] ^ v[c], 63);
        }
    }
}
